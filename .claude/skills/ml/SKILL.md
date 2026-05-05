# ML Pipeline & MLOps Rules

> Stack: XGBoost + MLflow + ONNX Runtime + SetFit + Great Expectations + DVC + SHAP

## Nguyên Tắc Cốt Lõi

> **Training-Serving Parity:** FeatureExtractor class PHẢI được dùng chung cho cả training pipeline lẫn prediction endpoint. Không bao giờ duplicate feature logic.

## FeatureExtractor Pattern (BẮT BUỘC)

```python
# ml/features/task_extractor.py — dùng chung cho train + serve
class TaskFeatureExtractor:
    """Single source of truth for all feature transformations."""

    def extract(self, task: dict | Task) -> dict:
        """Accepts both DB ORM object and raw dict (từ API request)."""
        if hasattr(task, '__dict__'):   # ORM object
            data = {c.name: getattr(task, c.name) for c in task.__table__.columns}
        else:
            data = task

        return {
            "title_len":          len(data.get("title", "")),
            "desc_tokens":        len(data.get("description", "").split()),
            "priority_score":     data.get("priority_score", 3),
            "has_deadline":       1 if data.get("deadline") else 0,
            "dependency_count":   data.get("dependency_count", 0),
            "subtask_count":      data.get("subtask_count", 0),
            "created_dow":        data.get("created_day_of_week", 0),
            "deadline_buffer_hrs": data.get("deadline_buffer_hrs", 0),
            "assignee_workload":  data.get("assignee_workload", 0.5),
            "revision_count":     data.get("revision_count", 0),
        }

# Training pipeline:
extractor = TaskFeatureExtractor()
X = pd.DataFrame([extractor.extract(t) for t in training_tasks])

# Prediction endpoint:
features = extractor.extract(task_from_request)
prediction = model.predict([list(features.values())])
```

## Data Validation (Great Expectations)

```python
# ml/evaluation/data_validation.py
# Chạy TRƯỚC mọi training run
import great_expectations as gx

def validate_training_data(df: pd.DataFrame) -> bool:
    context = gx.get_context()
    suite = context.get_expectation_suite("task_training")

    results = context.run_validation_operator(
        "action_list_operator",
        assets_to_validate=[(context.get_batch(df), suite)],
    )
    if not results["success"]:
        raise ValueError("Data validation failed — check GE report before training")
    return True

# Expectations chuẩn:
# ExpectColumnValuesToNotBeNull("actual_time")
# ExpectColumnValuesToBeBetween("estimated_time", min_value=0.1, max_value=2000)
# ExpectColumnValuesToBeUnique("task_id")
# ExpectColumnValuesToBeBetween("priority_score", min_value=1, max_value=5)
```

## MLflow Experiment Tracking

```python
# ml/training/train_predictor.py
import mlflow

def train(X_train, y_train, X_val, y_val):
    with mlflow.start_run(run_name=f"xgboost-{datetime.now():%Y%m%d-%H%M}"):
        # Log params
        params = {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05}
        mlflow.log_params(params)

        # Log dataset version
        mlflow.log_param("dvc_dataset_tag", get_dvc_tag())

        model = xgb.XGBRegressor(**params)
        model.fit(X_train, y_train)

        # Log metrics
        mae = mean_absolute_error(y_val, model.predict(X_val))
        rmse = mean_squared_error(y_val, model.predict(X_val), squared=False)
        mlflow.log_metrics({"val_mae": mae, "val_rmse": rmse})

        # Log SHAP feature importance
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_val[:100])
        mlflow.log_dict(
            {feat: float(imp) for feat, imp in zip(X_train.columns, abs(shap_values).mean(0))},
            "feature_importance.json"
        )

        # Export ONNX — KHÔNG dùng pickle
        onnx_model = skl2onnx.convert_sklearn(model, initial_types=[...])
        mlflow.onnx.log_model(onnx_model, "model")

        return mlflow.active_run().info.run_id
```

## Model Registry & Promotion

```python
# Các stages: Staging → Shadow → Production
# KHÔNG promote thẳng từ Staging lên Production

client = mlflow.tracking.MlflowClient()

# Promote to Shadow (chạy song song, không serve user)
client.transition_model_version_stage(
    name="task-time-predictor",
    version=new_version,
    stage="Shadow",
)

# Sau 1 tuần shadow monitoring → promote if shadow_mae < prod_mae
if shadow_mae < prod_mae * 0.95:   # Phải tốt hơn 5%
    client.transition_model_version_stage(
        name="task-time-predictor",
        version=new_version,
        stage="Production",
    )
```

## Shadow Mode Pattern

```python
# backend/src/services/prediction.service.py
async def predict_time(task: Task) -> PredictionOut:
    features = extractor.extract(task)
    prod_pred = prod_model.run(None, {"input": [features]})[0][0]

    # Shadow: chạy song song, chỉ log
    if shadow_model:
        shadow_pred = shadow_model.run(None, {"input": [features]})[0][0]
        mlflow.log_metric("shadow_prediction", shadow_pred)
        # Sau khi task done, drift_monitor so sánh với actual_time

    return PredictionOut(
        predicted_hours=round(float(prod_pred), 1),
        explanation=get_shap_explanation(features),
    )
```

## SHAP Explainability

```python
# Trả về cùng prediction endpoint
def get_shap_explanation(features: dict) -> dict:
    shap_vals = explainer.shap_values(pd.DataFrame([features]))
    impacts = sorted(
        zip(features.keys(), shap_vals[0]),
        key=lambda x: abs(x[1]), reverse=True
    )[:3]  # Top 3 factors
    return {
        factor: f"{'+' if val > 0 else ''}{val:.1f}h"
        for factor, val in impacts
    }
```

## Model Drift Monitoring

```python
# backend/src/workers/drift_monitor.py
@celery.task
def check_model_drift():
    """Chạy mỗi tuần qua Celery Beat."""
    completed = get_completed_tasks_last_7_days()
    if len(completed) < 50:
        return  # Không đủ sample để đánh giá

    predictions = [get_stored_prediction(t.id) for t in completed]
    actuals = [t.actual_time for t in completed]
    current_mae = mean_absolute_error(actuals, predictions)

    mlflow.log_metric("production_mae_weekly", current_mae)
    logger.info("drift_check", mae=current_mae, threshold=DRIFT_THRESHOLD)

    if current_mae > DRIFT_THRESHOLD:
        trigger_retraining_pipeline.delay()
        notify_slack(f"⚠️ Model drift: MAE={current_mae:.2f}h > threshold={DRIFT_THRESHOLD}h")
```

## DVC Dataset Versioning

```bash
# Sau mỗi lần cập nhật dataset
dvc add ml/data/tasks_training.csv
dvc push
git add ml/data/tasks_training.csv.dvc
git commit -m "data(tasks): add 10k augmented samples, total=50k"
git tag dataset-v2.0

# Khi train, log dataset tag vào MLflow
mlflow.log_param("dvc_dataset_tag", "dataset-v2.0")
```

## Self-Check

```
[ ] FeatureExtractor dùng chung cho train và serve (không duplicate)
[ ] Great Expectations validate data trước mỗi training run
[ ] MLflow log đủ: params, metrics, SHAP, DVC dataset tag
[ ] Export ONNX — không dùng pickle
[ ] Model mới đi qua Shadow stage trước khi promote Production
[ ] SHAP explanation được trả về cùng prediction
[ ] Drift monitor job đã được schedule trong Celery Beat
[ ] DVC push sau mỗi lần thay đổi dataset
```
