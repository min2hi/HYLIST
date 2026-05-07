"""
MLService — ONNX Runtime Inference Singleton (ADR-002).

Design:
  - Load ONNX model 1 lan khi app startup (khong reload moi request)
  - ONNX Runtime session la thread-safe -> khong can lock
  - Graceful degradation: neu model chua co -> tra ve rule-based fallback
  - Latency: p50 < 5ms, p99 < 50ms (ONNX Runtime tren CPU)

Su dung:
  ml_service = MLService()
  result = await ml_service.predict(task_data_dict)
"""
from __future__ import annotations

import json

# ml/ nam o repo root (ngoai backend/) — them vao sys.path
import sys as _sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import structlog

# TaskFeatureExtractor duoc import lazy ben trong initialize()
# Tranh keo pandas vao CI khi collect test (pandas nam trong ml/requirements.txt)

logger = structlog.get_logger(__name__)

# Duong dan model artifacts
_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # HYLIST/
_MODELS_DIR = _REPO_ROOT / "ml" / "models"
_ONNX_PATH = _MODELS_DIR / "priority_predictor_v1.onnx"
_META_PATH = _MODELS_DIR / "feature_names_v1.json"


class PredictionResult:
    """Ket qua prediction tra ve cho API."""

    __slots__ = (
        "predicted_hours",
        "confidence",
        "model_version",
        "latency_ms",
        "fallback",
        "shap_values",
        "shap_base_value",
    )

    def __init__(
        self,
        predicted_hours: float,
        confidence: float,
        model_version: str,
        latency_ms: float,
        fallback: bool = False,
        shap_values: dict[str, float] | None = None,
        shap_base_value: float | None = None,
    ) -> None:
        self.predicted_hours = predicted_hours
        self.confidence = confidence
        self.model_version = model_version
        self.latency_ms = latency_ms
        self.fallback = fallback  # True neu dung rule-based (model chua co)
        self.shap_values = shap_values
        self.shap_base_value = shap_base_value

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicted_hours": round(self.predicted_hours, 2),
            "confidence": round(self.confidence, 3),
            "model_version": self.model_version,
            "latency_ms": round(self.latency_ms, 2),
            "fallback": self.fallback,
            "shap_values": self.shap_values,
            "shap_base_value": self.shap_base_value,
        }


class MLService:
    """
    Singleton ML inference service.
    Load ONNX model mot lan, reuse cho moi request.
    """

    _instance: MLService | None = None
    _session: Any = None  # onnxruntime.InferenceSession
    _explainer: Any = None  # shap.TreeExplainer
    _extractor: Any = None  # TaskFeatureExtractor (lazy import)
    _model_version: str = "unknown"
    _input_name: str = "float_input"

    def __new__(cls) -> MLService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def initialize(self) -> None:
        """
        Goi khi app startup (trong lifespan event).
        Load ONNX model vao memory.
        """
        if self._initialized:
            return

        # Lazy import — tranh keo pandas vao CI khi chi install backend deps
        _ml_root = Path(__file__).parent.parent.parent.parent  # HYLIST/
        if str(_ml_root) not in _sys.path:
            _sys.path.insert(0, str(_ml_root))

        from ml.features.task_extractor import TaskFeatureExtractor  # noqa: PLC0415

        self._extractor = TaskFeatureExtractor()

        if not _ONNX_PATH.exists():
            logger.warning(
                "ml_model_not_found",
                path=str(_ONNX_PATH),
                fallback="rule-based",
            )
            self._initialized = True
            return

        try:
            import onnxruntime as rt

            # GraphOptimizationLevel.ORT_ENABLE_ALL cho performance tot nhat
            opts = rt.SessionOptions()
            opts.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.intra_op_num_threads = 1  # Single thread vi moi request la 1 sample
            opts.inter_op_num_threads = 1

            self._session = rt.InferenceSession(str(_ONNX_PATH), sess_options=opts)
            self._input_name = self._session.get_inputs()[0].name

            # Doc metadata
            ubj_path = None
            if _META_PATH.exists():
                meta = json.loads(_META_PATH.read_text(encoding="utf-8"))
                self._model_version = meta.get("feature_version", "v1")
                ubj_path = meta.get("ubj_model_path")

            # Khoi tao SHAP Explainer voi UBJ model
            if ubj_path and Path(ubj_path).exists():
                try:
                    import shap
                    import xgboost as xgb

                    booster = xgb.Booster()
                    booster.load_model(ubj_path)
                    self._explainer = shap.TreeExplainer(booster)
                    logger.info("shap_explainer_loaded", path=ubj_path)
                except Exception as e:
                    logger.error("shap_explainer_failed", error=str(e))

            logger.info(
                "ml_model_loaded",
                path=str(_ONNX_PATH),
                version=self._model_version,
                input_name=self._input_name,
            )
        except Exception as e:
            logger.error("ml_model_load_failed", error=str(e))
            self._session = None

        self._initialized = True

    async def predict(self, task_data: dict[str, Any]) -> PredictionResult:
        """
        Chay ONNX inference cho 1 task.

        Args:
            task_data: dict chua cac fields cua task
                       (title, description, priority_score, deadline,
                        assignee_workload, revision_count, tags, ...)

        Returns:
            PredictionResult voi predicted_hours va confidence
        """
        t_start = time.perf_counter()

        # Neu model chua load -> fallback rule-based
        if self._session is None:
            return self._rule_based_fallback(task_data, t_start)

        try:
            # Feature extraction (dung TaskFeatureExtractor giong training)
            features = self._extractor.transform(task_data)  # shape (1, 13), np.ndarray

            # ONNX Runtime chi nhan float32
            features_f32 = features.astype(np.float32)

            # Inference
            preds = self._session.run(None, {self._input_name: features_f32})
            predicted_hours = float(preds[0].flatten()[0])

            # Clip: actual_time < 0 la vo nghia
            predicted_hours = max(0.1, predicted_hours)

            latency_ms = (time.perf_counter() - t_start) * 1000

            # SHAP Explanations
            shap_values = None
            shap_base = None
            if self._explainer is not None:
                # TreeExplainer nhan numpy array truc tiep
                shap_res = self._explainer(features_f32)
                # values.shape = (1, 13) -> lay row 0
                sv = shap_res.values[0]
                base = shap_res.base_values[0]
                shap_base = float(base)
                # Map feature values (lam tron 4 chu so de JSON nhe)
                shap_values = {
                    feat: round(float(val), 4)
                    for feat, val in zip(self._extractor.FEATURE_NAMES, sv, strict=False)
                }

            # Confidence: heuristic don gian (co the dung SHAP variance sau)
            # Low priority + no deadline = low confidence
            priority = float(task_data.get("priority_score", 3))
            confidence = min(0.95, 0.5 + (priority - 1) * 0.1)

            logger.info(
                "ml_prediction",
                predicted_hours=round(predicted_hours, 2),
                confidence=round(confidence, 3),
                latency_ms=round(latency_ms, 2),
            )

            return PredictionResult(
                predicted_hours=predicted_hours,
                confidence=confidence,
                model_version=self._model_version,
                latency_ms=latency_ms,
                shap_values=shap_values,
                shap_base_value=shap_base,
            )

        except Exception as e:
            logger.error("ml_inference_failed", error=str(e))
            return self._rule_based_fallback(task_data, t_start)

    def _rule_based_fallback(
        self, task_data: dict[str, Any], t_start: float
    ) -> PredictionResult:
        """
        Fallback khi ONNX model chua co hoac bi loi.
        Rule don gian dua tren priority_score.
        """
        priority = int(task_data.get("priority_score", 3))
        # Mapping priority -> estimated hours (rule of thumb)
        priority_hours = {1: 1.0, 2: 2.0, 3: 4.0, 4: 6.0, 5: 8.0}
        predicted = priority_hours.get(priority, 4.0)
        latency_ms = (time.perf_counter() - t_start) * 1000

        logger.warning(
            "ml_fallback_used",
            reason="model_not_available",
            predicted_hours=predicted,
        )

        return PredictionResult(
            predicted_hours=predicted,
            confidence=0.3,  # Low confidence cho fallback
            model_version="rule-based-fallback",
            latency_ms=latency_ms,
            fallback=True,
        )

    @property
    def is_ready(self) -> bool:
        """True neu ONNX model da load thanh cong."""
        return self._initialized and self._session is not None

    @property
    def model_version(self) -> str:
        return self._model_version


# Module-level singleton instance
ml_service = MLService()
