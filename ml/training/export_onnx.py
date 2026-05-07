"""
HYLIST Phase 2 — XGBoost -> ONNX Export (ADR-002).

Tại sao ONNX thay pickle?
  - pickle: arbitrary code execution risk khi load untrusted model
  - ONNX: open format, cross-platform, ONNX Runtime nhanh hơn ~2x
  - Versioned: models/priority_predictor_v1.onnx — dễ rollback

Cách chạy:
    cd HYLIST/
    python ml/training/export_onnx.py

Output:
    ml/models/priority_predictor_v1.onnx
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import joblib
import numpy as np
import onnx
import onnxmltools
import onnxruntime as rt
from onnxmltools.convert.common.data_types import FloatTensorType
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType as SKL2ONNXFloat

from ml.features.task_extractor import FEATURE_VERSION, TaskFeatureExtractor

MODELS_DIR = _REPO_ROOT / "ml" / "models"
PKL_PATH = MODELS_DIR / "priority_predictor_v1.pkl"
ONNX_PATH = MODELS_DIR / "priority_predictor_v1.onnx"
META_PATH = MODELS_DIR / "feature_names_v1.json"


def load_xgboost_model():
    """Load XGBoost model từ .pkl (intermediate format)."""
    if not PKL_PATH.exists():
        raise FileNotFoundError(
            f"Model file not found: {PKL_PATH}\n"
            "Chay: python ml/training/train.py truoc."
        )
    print(f"[LOAD] Loading XGBoost model from: {PKL_PATH}")
    model = joblib.load(PKL_PATH)
    print(f"   Type: {type(model).__name__}")
    print(f"   n_estimators: {model.n_estimators}")
    return model


def export_to_onnx(model, n_features: int) -> None:
    """
    Convert XGBoost model sang ONNX format.

    Workaround: onnxmltools chi ho tro feature names dang 'f0', 'f1'...
    Nen re-train booster voi feature names numeric truoc khi convert.
    Feature mapping duoc luu trong feature_names_v1.json.
    """
    import copy
    import tempfile

    print(f"\n[CONVERT] Converting to ONNX (n_features={n_features})...")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Buoc 1: Luu booster ra JSON, re-load voi feature names dang f0..f12
    booster = model.get_booster()
    with tempfile.NamedTemporaryFile(suffix=".ubj", delete=False) as tmp:
        tmp_path = tmp.name
    booster.save_model(tmp_path)

    # Load lai va reset feature names sang format onnxmltools chap nhan
    from xgboost import Booster
    new_booster = Booster()
    new_booster.load_model(tmp_path)
    new_booster.feature_names = [f"f{i}" for i in range(n_features)]
    Path(tmp_path).unlink(missing_ok=True)

    # Buoc 2: Wrap lai thanh XGBRegressor de onnxmltools xu ly
    import xgboost as xgb
    temp_model = copy.copy(model)
    temp_model._Booster = new_booster

    # Buoc 3: Convert via onnxmltools
    initial_type = [("float_input", FloatTensorType([None, n_features]))]
    onnx_model = onnxmltools.convert_xgboost(
        temp_model,
        name="HYLISTTaskTimePredictor",
        initial_types=initial_type,
    )

    # Validate
    onnx.checker.check_model(onnx_model)
    print("   ONNX model validated OK")

    # Save ONNX
    with open(ONNX_PATH, "wb") as f:
        f.write(onnx_model.SerializeToString())

    size_kb = ONNX_PATH.stat().st_size / 1024
    print(f"[SAVE] ONNX model saved: {ONNX_PATH} ({size_kb:.1f} KB)")

    # Buoc 4: Luu XGBoost native format (.ubj) de dung cho SHAP Explainer
    # .ubj (Universal Binary JSON) la format an toan, khong dung pickle -> Tuan thu ADR-002
    UBJ_PATH = MODELS_DIR / f"priority_predictor_{FEATURE_VERSION}.ubj"
    booster.save_model(str(UBJ_PATH))
    print(f"[SAVE] XGBoost native model (for SHAP) saved: {UBJ_PATH}")


def verify_parity(model, onnx_path: Path, n_features: int) -> None:
    """
    CRITICAL: Verify XGBoost predict() == ONNX Runtime predict().
    Neu khac nhau -> Training-Serving Skew.
    """
    print("\n[PARITY] Verifying XGBoost == ONNX Runtime predictions...")

    # Tao sample input
    rng = np.random.default_rng(42)
    X_sample = rng.random((20, n_features)).astype(np.float32)

    # XGBoost prediction
    xgb_preds = model.predict(X_sample)

    # ONNX Runtime prediction
    sess = rt.InferenceSession(str(onnx_path))
    input_name = sess.get_inputs()[0].name
    onnx_preds = sess.run(None, {input_name: X_sample})[0].flatten()

    # Compare
    max_diff = float(np.max(np.abs(xgb_preds - onnx_preds)))
    mean_diff = float(np.mean(np.abs(xgb_preds - onnx_preds)))

    print(f"   Max diff:  {max_diff:.8f}h")
    print(f"   Mean diff: {mean_diff:.8f}h")

    if max_diff > 0.01:
        raise RuntimeError(
            f"PARITY FAIL: max diff {max_diff:.4f}h > 0.01h. "
            "XGBoost va ONNX cho ket qua khac nhau. Kiem tra lai convert."
        )

    print("   [OK] Parity check PASSED (max diff < 0.01h)")


def benchmark_latency(onnx_path: Path, n_features: int) -> None:
    """Do latency ONNX Runtime inference."""
    import time

    sess = rt.InferenceSession(str(onnx_path))
    input_name = sess.get_inputs()[0].name

    # Single sample inference (serving case)
    X_single = np.random.default_rng(0).random((1, n_features)).astype(np.float32)

    # Warm up
    for _ in range(10):
        sess.run(None, {input_name: X_single})

    # Benchmark 1000 calls
    n_calls = 1000
    start = time.perf_counter()
    for _ in range(n_calls):
        sess.run(None, {input_name: X_single})
    elapsed_ms = (time.perf_counter() - start) * 1000

    p_avg = elapsed_ms / n_calls
    print(f"\n[BENCH] Latency ({n_calls} calls, single sample):")
    print(f"   Average: {p_avg:.3f}ms")
    print(f"   Projected p99: ~{p_avg * 3:.1f}ms")

    if p_avg > 50:
        print(f"   [WARN] Average {p_avg:.1f}ms > 50ms target. Consider batching.")
    else:
        print(f"   [OK] Well within 100ms p99 SLO target.")


def update_metadata(onnx_path: Path) -> None:
    """Cap nhat feature_names_v1.json voi duong dan ONNX va UBJ model."""
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        meta["onnx_model_path"] = str(onnx_path)
        meta["ubj_model_path"] = str(MODELS_DIR / f"priority_predictor_{FEATURE_VERSION}.ubj")
        meta["onnx_exported"] = True
        META_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        print(f"\n[SAVE] Metadata updated: {META_PATH}")


def run_export() -> None:
    extractor = TaskFeatureExtractor()
    n_features = len(extractor.FEATURE_NAMES)

    # 1. Load XGBoost model
    model = load_xgboost_model()

    # 2. Export to ONNX
    export_to_onnx(model, n_features)

    # 3. Verify parity (CRITICAL)
    verify_parity(model, ONNX_PATH, n_features)

    # 4. Benchmark latency
    benchmark_latency(ONNX_PATH, n_features)

    # 5. Update metadata
    update_metadata(ONNX_PATH)

    print(f"\n{'='*60}")
    print("[OK] ONNX export complete!")
    print(f"   Model: {ONNX_PATH}")
    print(f"   Ready for: backend/src/services/ml_service.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_export()
