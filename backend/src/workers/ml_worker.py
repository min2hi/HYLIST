"""
Celery worker tasks for Machine Learning operations (Phase 2 placeholder).
"""
import time
import structlog
from src.core.celery_app import celery_app

logger = structlog.get_logger(__name__)

@celery_app.task(name="ml.predict_task_priority", bind=True, max_retries=3)
def predict_task_priority(self, task_id: str) -> dict:
    """
    Dummy ML prediction task for Phase 1 -> 2 transition.
    Sẽ được thay thế bằng code gọi XGBoost Model thật ở Phase 2.
    """
    logger.info("ml_predict_started", task_id=task_id)
    
    # Simulate inference delay (50ms - 200ms)
    time.sleep(0.1)
    
    # Placeholder response
    predicted_priority = 3
    confidence = 0.85
    
    logger.info(
        "ml_predict_finished", 
        task_id=task_id, 
        predicted_priority=predicted_priority,
        confidence=confidence
    )
    
    return {
        "task_id": task_id,
        "predicted_priority": predicted_priority,
        "confidence": confidence,
        "status": "success"
    }
