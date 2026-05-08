"""
Parity Tests: XGBoost Native vs ONNX Runtime

Muc dich:
Dam bao rang khi model chay trong moi truong production (ONNX Runtime, C++ backend)
se cho ket qua hoan toan giong voi moi truong training (XGBoost Python).
Day la buoc kiem tra Training-Serving Skew quan trong nhat truoc khi deploy.

Note: Yeu cau ML deps (pandas, xgboost, onnxruntime, shap).
      CI backend-only se tu dong skip module nay.
"""

import json
from pathlib import Path

import pytest

# Skip module neu ML deps chua duoc install (CI backend-only)
pytest.importorskip("pandas", reason="ML deps not installed (ml/requirements.txt)")
pytest.importorskip("xgboost", reason="ML deps not installed (ml/requirements.txt)")
pytest.importorskip("onnxruntime", reason="ML deps not installed (ml/requirements.txt)")


from ml.features.task_extractor import TaskFeatureExtractor  # noqa: E402

from src.services.ml_service import ml_service  # noqa: E402

# Thu muc chua model da train
_MODELS_DIR = Path(__file__).parent.parent.parent.parent / "ml" / "models"


@pytest.fixture(scope="module")
def onnx_ready():
    """Dam bao MLService da load ONNX model (fallback se lam fail test)."""
    if not ml_service.is_ready:
        ml_service.initialize()
    if not ml_service.is_ready:
        pytest.skip("ONNX model khong ton tai. Hay chay export_onnx.py truoc.")
    return True


@pytest.fixture(scope="module")
def xgb_booster():
    """Load XGBoost native model (.ubj) de so sanh."""
    import xgboost as xgb

    meta_path = _MODELS_DIR / "feature_names_v1.json"
    if not meta_path.exists():
        pytest.skip("Metadata khong ton tai.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ubj_path = meta.get("ubj_model_path")

    if not ubj_path or not Path(ubj_path).exists():
        pytest.skip("UBJ model khong ton tai. Hay chay export_onnx.py truoc.")

    booster = xgb.Booster()
    booster.load_model(ubj_path)
    return booster


@pytest.mark.asyncio
async def test_inference_parity(onnx_ready, xgb_booster):
    """
    Kiem tra chenh lech giua ONNX va XGBoost cho mot so sample data.
    Gioi han max diff = 0.01h (khoang 36 giay).
    """
    import xgboost as xgb

    # 1. Tao mock data
    mock_tasks = [
        {
            "title": "Fix critical bug in payment API",
            "description": "Payment gateway is failing for 5% of users. High priority.",
            "priority_score": 5,
            "deadline": None,
            "assignee_workload": 2,
            "revision_count": 0,
            "tags": ["bug", "backend", "critical"],
            "estimated_time": 4.0,
        },
        {
            "title": "Update documentation",
            "description": "Add new API endpoints to swagger docs.",
            "priority_score": 2,
            "deadline": "2026-12-31T23:59:59Z",
            "assignee_workload": 5,
            "revision_count": 1,
            "tags": ["docs", "api"],
            "estimated_time": 1.5,
        },
    ]

    extractor = TaskFeatureExtractor()

    for task_data in mock_tasks:
        # --- 2. XGBoost Inference ---
        features = extractor.transform(task_data)
        dmatrix = xgb.DMatrix(features, feature_names=extractor.FEATURE_NAMES)
        xgb_pred = float(xgb_booster.predict(dmatrix)[0])
        xgb_pred = max(0.1, xgb_pred)  # Apply same clipping as ml_service

        # --- 3. ONNX Inference (via MLService) ---
        prediction = await ml_service.predict(task_data)
        onnx_pred = prediction.predicted_hours

        # --- 4. So sanh Parity ---
        diff = abs(xgb_pred - onnx_pred)

        # In ket qua de verify
        print(f"\nTask: {task_data['title']}")
        print(f"XGBoost: {xgb_pred:.6f}h")
        print(f"ONNX:    {onnx_pred:.6f}h")
        print(f"Diff:    {diff:.8f}h")

        # ASSERT: Sai so giua 2 he thong phai be hon 0.01 gio
        assert diff < 0.01, f"Parity failed! Diff {diff}h vuot nguong 0.01h"

        # Verify rang SHAP values cung duoc tra ve va on dinh
        if prediction.shap_values:
            assert len(prediction.shap_values) == len(extractor.FEATURE_NAMES)
            assert prediction.shap_base_value is not None
