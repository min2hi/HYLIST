"""
HYLIST Phase 2 — XGBoost Training Pipeline.

Mục tiêu: Dự đoán actual_time (giờ thực tế làm task) từ task features.
Target: Regression — predict float (hours)
Metric chính: MAE (Mean Absolute Error) — dễ giải thích với user

Cách chạy:
    cd HYLIST/
    python ml/training/train.py

MLflow UI:
    http://localhost:5001  (sau khi docker-compose up mlflow)

Output:
    ml/models/priority_predictor_v1.pkl   ← XGBoost model (intermediate)
    ml/models/feature_names_v1.json       ← Feature metadata
    MLflow run với đầy đủ params + metrics + artifacts
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Thêm repo root vào path để import ml/
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import joblib
import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, train_test_split
from xgboost import XGBRegressor

from ml.features.task_extractor import FEATURE_VERSION, TaskFeatureExtractor

# ── Config ────────────────────────────────────────────────────────────────────

DATA_PATH = _REPO_ROOT / "ml" / "data" / "tasks_training.csv"
MODELS_DIR = _REPO_ROOT / "ml" / "models"
MODEL_VERSION = FEATURE_VERSION  # Phải khớp với extractor version

# XGBoost hyperparameters (baseline — sẽ tune bằng Optuna ở Phase 2b)
XGBOOST_PARAMS: dict = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "gamma": 0.1,
    "reg_alpha": 0.1,    # L1 regularization
    "reg_lambda": 1.0,   # L2 regularization
    "objective": "reg:squarederror",
    "eval_metric": "mae",
    "random_state": 42,
    "n_jobs": -1,
}

# MLflow tracking URI — SQLite backend (MLflow 3.x khuyến nghị, hỗ trợ Windows)
# File store (file://) bị deprecated từ Feb 2026 và không hỗ trợ Windows path
_MLFLOW_DB = _REPO_ROOT / "ml" / "mlruns" / "mlflow.db"
_MLFLOW_DB.parent.mkdir(parents=True, exist_ok=True)
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{_MLFLOW_DB}",
)
MLFLOW_EXPERIMENT = "hylist-task-time-predictor"

# Rollback threshold: nếu MAE > này thì không promote model
MAE_THRESHOLD_HOURS = 3.0  # p50 task thực tế ~ 3.6h, MAE 3h là acceptable


# ── Main Pipeline ─────────────────────────────────────────────────────────────


def load_and_validate_data(path: Path) -> pd.DataFrame:
    """
    Load CSV và validate cơ bản.
    Chỉ lấy completed tasks (status=done) — có actual_time là label thật.
    """
    print(f"[DIR] Loading data from: {path}")
    df = pd.read_csv(path)
    print(f"   Raw rows: {len(df):,}")

    # Chỉ train trên completed tasks — những task có actual_time thật
    df_done = df[df["status"] == "done"].copy()
    df_done = df_done.dropna(subset=["actual_time"])
    print(f"   Completed tasks with actual_time: {len(df_done):,}")

    if len(df_done) < 500:
        raise ValueError(
            f"Không đủ training data: {len(df_done)} rows (cần ≥ 500). "
            "Chạy mock_generator.py để tạo thêm data."
        )

    # Clip outliers: actual_time > 100h là bất thường
    before = len(df_done)
    df_done = df_done[df_done["actual_time"] <= 100]
    clipped = before - len(df_done)
    if clipped > 0:
        print(f"   [WARN]  Clipped {clipped} outlier rows (actual_time > 100h)")

    return df_done


def extract_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """
    Chạy TaskFeatureExtractor trên training data.
    Đây là bước QUAN TRỌNG nhất — phải giống hệt serving path.
    """
    print(f"\n[FEAT] Extracting features (extractor version: {FEATURE_VERSION})")
    extractor = TaskFeatureExtractor()
    X = extractor.transform(df)
    y = df["actual_time"].reset_index(drop=True)

    print(f"   Features: {list(X.columns)}")
    print(f"   X shape: {X.shape}, y shape: {y.shape}")
    print(f"   Target — mean: {y.mean():.2f}h, std: {y.std():.2f}h, max: {y.max():.1f}h")

    return X, y


def cross_validate(X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    """
    5-fold cross-validation để estimate generalization error.
    Trả về mean metrics trên CV.
    """
    print("\n[SPLIT] Running 5-fold cross-validation...")
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_maes = []
    cv_rmses = []

    for fold, (train_idx, val_idx) in enumerate(kf.split(X), 1):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        model = XGBRegressor(**XGBOOST_PARAMS)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        preds = model.predict(X_val)
        mae = mean_absolute_error(y_val, preds)
        rmse = np.sqrt(mean_squared_error(y_val, preds))
        cv_maes.append(mae)
        cv_rmses.append(rmse)
        print(f"   Fold {fold}: MAE={mae:.3f}h  RMSE={rmse:.3f}h")

    results = {
        "cv_mae_mean": float(np.mean(cv_maes)),
        "cv_mae_std": float(np.std(cv_maes)),
        "cv_rmse_mean": float(np.mean(cv_rmses)),
        "cv_rmse_std": float(np.std(cv_rmses)),
    }
    print(f"\n   CV MAE: {results['cv_mae_mean']:.3f} ± {results['cv_mae_std']:.3f}h")
    return results


def train_final_model(
    X_train: pd.DataFrame, y_train: pd.Series,
    X_test: pd.DataFrame, y_test: pd.Series,
) -> tuple[XGBRegressor, dict[str, float]]:
    """
    Train model cuối trên full train set, evaluate trên held-out test set.
    """
    print("\n[TRAIN] Training final model on full train set...")
    model = XGBRegressor(**XGBOOST_PARAMS)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=100,
    )

    preds = model.predict(X_test)
    metrics = {
        "test_mae": float(mean_absolute_error(y_test, preds)),
        "test_rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
        "test_r2": float(r2_score(y_test, preds)),
        "test_samples": len(y_test),
    }

    print(f"\n[STATS] Test Set Results:")
    print(f"   MAE  = {metrics['test_mae']:.3f}h  (target: < {MAE_THRESHOLD_HOURS}h)")
    print(f"   RMSE = {metrics['test_rmse']:.3f}h")
    print(f"   R²   = {metrics['test_r2']:.3f}  (1.0 = perfect)")

    return model, metrics


def check_promotion_criteria(metrics: dict[str, float]) -> bool:
    """
    Champion/Challenger: model mới được promote nếu vượt threshold.
    """
    mae = metrics["test_mae"]
    if mae <= MAE_THRESHOLD_HOURS:
        print(f"\n[OK] MAE {mae:.3f}h <= threshold {MAE_THRESHOLD_HOURS}h -> PROMOTE model")
        return True
    else:
        print(f"\n[FAIL] MAE {mae:.3f}h > threshold {MAE_THRESHOLD_HOURS}h -> DO NOT PROMOTE")
        print("   Xem xét: tune hyperparameters hoặc thêm features")
        return False


def save_artifacts(
    model: XGBRegressor,
    extractor: TaskFeatureExtractor,
    metrics: dict,
    cv_metrics: dict,
    run_id: str,
) -> None:
    """Lưu model artifacts ra disk."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. XGBoost model (dùng joblib — intermediate, sẽ convert sang ONNX ở Tuần 7)
    model_path = MODELS_DIR / f"priority_predictor_{MODEL_VERSION}.pkl"
    joblib.dump(model, model_path)
    print(f"\n[SAVE] Model saved: {model_path}")

    # 2. Feature metadata — dùng khi load model để verify compatibility
    metadata = {
        "feature_version": FEATURE_VERSION,
        "feature_names": extractor.get_feature_names(),
        "target": "actual_time",
        "target_unit": "hours",
        "mlflow_run_id": run_id,
        "metrics": {**metrics, **cv_metrics},
        "xgboost_params": XGBOOST_PARAMS,
    }
    meta_path = MODELS_DIR / f"feature_names_{MODEL_VERSION}.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"[SAVE] Metadata saved: {meta_path}")


def run_training() -> None:
    """
    Main training pipeline với MLflow tracking.
    """
    # ── Setup MLflow ──────────────────────────────────────────────────────────
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    print(f"\n[MLFLOW] MLflow tracking URI: {MLFLOW_TRACKING_URI}")
    print(f"   Experiment: {MLFLOW_EXPERIMENT}")

    # ── Load data ─────────────────────────────────────────────────────────────
    df = load_and_validate_data(DATA_PATH)

    # ── Extract features ──────────────────────────────────────────────────────
    extractor = TaskFeatureExtractor()
    X, y = extract_features(df)

    # ── Split: 70% train / 15% val (CV) / 15% test ───────────────────────────
    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )
    print(f"\n[PKG] Split: train={len(X_train_full):,}  test={len(X_test):,}")

    # ── MLflow Run ────────────────────────────────────────────────────────────
    with mlflow.start_run(run_name=f"xgboost-{MODEL_VERSION}-baseline") as run:
        run_id = run.info.run_id
        print(f"\n[RUN] MLflow Run ID: {run_id}")

        # Log params
        mlflow.log_params(XGBOOST_PARAMS)
        mlflow.log_param("feature_version", FEATURE_VERSION)
        mlflow.log_param("training_rows", len(X_train_full))
        mlflow.log_param("test_rows", len(X_test))
        mlflow.log_param("target", "actual_time")

        # Cross-validation
        cv_metrics = cross_validate(X_train_full, y_train_full)
        mlflow.log_metrics(cv_metrics)

        # Train final model
        model, test_metrics = train_final_model(
            X_train_full, y_train_full, X_test, y_test
        )
        mlflow.log_metrics(test_metrics)

        # Log model natively với MLflow
        mlflow.xgboost.log_model(model, artifact_path="xgboost_model")

        # Promotion check
        should_promote = check_promotion_criteria(test_metrics)
        mlflow.log_param("promoted", should_promote)

        # Feature importance
        importance = dict(zip(extractor.get_feature_names(), model.feature_importances_))
        importance_sorted = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
        print("\n[CHART] Feature Importance (top 5):")
        for feat, imp in list(importance_sorted.items())[:5]:
            print(f"   {feat:30s}: {imp:.4f}")
        mlflow.log_dict(importance_sorted, "feature_importance.json")

        # Save artifacts
        if should_promote:
            save_artifacts(model, extractor, test_metrics, cv_metrics, run_id)

        print(f"\n{'='*60}")
        print(f"[OK] Training complete!")
        print(f"   MLflow Run: {run_id}")
        print(f"   View UI:    http://localhost:5001")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    run_training()
