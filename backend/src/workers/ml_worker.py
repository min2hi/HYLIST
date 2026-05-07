"""
Celery worker tasks for Machine Learning operations — Phase 2.

Task: predict_task_priority
  - Trigger: sau khi Task duoc tao (post-create hook tu task_service)
  - Action: chay ONNX inference via MLService
  - Shadow mode: luu ket qua vao ml_predictions table (Tuan 8)
  - Retry: max 3 lan voi exponential backoff
"""

import structlog

from src.core.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="ml.predict_task_priority",
    bind=True,
    max_retries=3,
    default_retry_delay=5,  # giay
)
def predict_task_priority(self, task_id: str, task_data: dict) -> dict:
    """
    Async ML prediction task.

    Args:
        task_id: UUID cua task can predict
        task_data: dict chua fields cua task (title, description, priority_score, ...)
                   Truyen truc tiep de tranh 1 round-trip DB trong worker

    Returns:
        dict: {task_id, predicted_hours, confidence, model_version, fallback}
    """
    import asyncio

    logger.info("ml_worker_predict_started", task_id=task_id)

    try:
        # Import day du khi worker chay (lazy import tranh circular)
        from src.services.ml_service import ml_service

        # Dam bao model da duoc initialize trong worker process
        if not ml_service._initialized:
            ml_service.initialize()

        # Chay inference (async method trong sync celery task)
        loop = asyncio.new_event_loop()
        try:
            prediction = loop.run_until_complete(ml_service.predict(task_data))
        finally:
            loop.close()

        result = {
            "task_id": task_id,
            "predicted_hours": prediction.predicted_hours,
            "confidence": prediction.confidence,
            "model_version": prediction.model_version,
            "latency_ms": prediction.latency_ms,
            "fallback": prediction.fallback,
            "shap_values": prediction.shap_values,
            "shap_base_value": prediction.shap_base_value,
            "status": "success",
        }

        logger.info(
            "ml_worker_predict_done",
            task_id=task_id,
            predicted_hours=prediction.predicted_hours,
            confidence=prediction.confidence,
            fallback=prediction.fallback,
        )

        # Luu vao ml_predictions table (Shadow mode)
        from src.core.database import get_db_context
        from src.models import MLPrediction

        async def _save_shadow():
            async with get_db_context() as db:
                ml_pred = MLPrediction(
                    task_id=task_id,
                    org_id=task_data["org_id"],  # Can task_data co org_id
                    model_version=prediction.model_version,
                    feature_version=prediction.model_version,  # Thuong giong nhau
                    predicted_hours=prediction.predicted_hours,
                    confidence=prediction.confidence,
                    fallback=prediction.fallback,
                    latency_ms=prediction.latency_ms,
                    shap_values=prediction.shap_values,
                    shap_base_value=prediction.shap_base_value,
                )
                db.add(ml_pred)
                await db.commit()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_save_shadow())
        finally:
            loop.close()

        return result

    except Exception as exc:
        logger.error(
            "ml_worker_predict_failed",
            task_id=task_id,
            error=str(exc),
            retry_count=self.request.retries,
        )
        # Retry voi exponential backoff
        raise self.retry(exc=exc, countdown=5 * (2**self.request.retries)) from exc
