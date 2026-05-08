"""
Celery worker tasks for NLP operations — Phase 3.

Task: tag_task_with_nlp
  - Trigger: sau khi Task duoc tao (post-create hook tu task_service)
  - Queue: nlp (xu ly boi nlp-worker container, co PyTorch)
  - Action: chay SetFit inference -> update task.tags trong DB -> publish SSE event
  - Retry: max 3 lan voi exponential backoff
  - Fallback: neu model chua co hoac inference that bai -> khong update tags (silent fail)

Design:
  - NLP worker KHONG lam bay DB request neu model chua san sang
  - Sau khi tag -> publish event qua Redis Pub/Sub -> SSE endpoint push ve frontend
  - Separate queue tu ml worker vi PyTorch rat nang, muon scale doc lap
"""

import structlog

from src.core.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="nlp.tag_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    queue="nlp",
)
def tag_task_with_nlp(
    self,
    task_id: str,
    task_title: str,
    task_description: str,
    org_id: str,
) -> dict:
    """
    Phan loai task thanh 1 trong 4 nhan: Bug / Feature / Urgent / Research.

    Args:
        task_id:          UUID cua task
        task_title:       Tieu de task (dung lam input cho NLP)
        task_description: Mo ta task
        org_id:           Org ID de multi-tenancy check khi update DB

    Returns:
        dict: {task_id, tag, confidence, fallback}
    """
    import asyncio

    logger.info("nlp_worker_tagging_started", task_id=task_id)

    try:
        # Lazy import — chi co trong nlp-worker container (Dockerfile.nlp)
        # API container KHONG co PyTorch, se khong bao gio import file nay
        import sys
        from pathlib import Path

        _ml_root = Path(__file__).parent.parent.parent.parent.parent  # HYLIST/
        if str(_ml_root) not in sys.path:
            sys.path.insert(0, str(_ml_root))

        from ml.nlp.tag_classifier import tag_classifier  # noqa: PLC0415

        # Dam bao model da duoc initialize
        if not tag_classifier._initialized:
            tag_classifier.initialize()

        # Chay inference
        text = f"{task_title}. {task_description}" if task_description else task_title
        predictions = tag_classifier.predict(text)

        if not predictions:
            logger.warning("nlp_no_prediction", task_id=task_id, fallback=True)
            return {"task_id": task_id, "tag": None, "confidence": 0.0, "fallback": True}

        top = predictions[0]
        tag = top.tag
        confidence = top.confidence

        logger.info(
            "nlp_prediction_done",
            task_id=task_id,
            tag=tag,
            confidence=round(confidence, 3),
        )

        # Update task.tags trong DB
        async def _update_task_tag() -> None:
            from sqlalchemy import select  # noqa: PLC0415

            from src.core.database import get_db_context  # noqa: PLC0415
            from src.models import Task  # noqa: PLC0415

            async with get_db_context() as db:
                stmt = select(Task).where(Task.id == task_id)
                result = await db.execute(stmt)
                task = result.scalar_one_or_none()
                if task:
                    # tags la list — append neu chua co, khong duplicate
                    existing_tags = list(task.tags or [])
                    if tag not in existing_tags:
                        existing_tags.append(tag)
                        task.tags = existing_tags
                    # Commit tu dong boi session.begin() context manager
                    logger.info("nlp_tag_saved", task_id=task_id, tags=existing_tags)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_update_task_tag())
        finally:
            loop.close()

        # Publish SSE event de frontend update real-time (Tuan 11)
        _publish_tag_event(task_id=task_id, org_id=org_id, tag=tag, confidence=confidence)

        return {
            "task_id": task_id,
            "tag": tag,
            "confidence": round(confidence, 3),
            "fallback": False,
        }

    except Exception as exc:
        logger.error(
            "nlp_worker_tag_failed",
            task_id=task_id,
            error=str(exc),
            retry_count=self.request.retries,
        )
        raise self.retry(exc=exc, countdown=10 * (2**self.request.retries)) from exc


def _publish_tag_event(task_id: str, org_id: str, tag: str, confidence: float) -> None:
    """
    Publish SSE event len Redis Pub/Sub.
    SSE endpoint (/api/v1/events/...) se nhan va push ve frontend.
    Dung asyncio.run() vi day la sync context (Celery task).
    """

    import redis as sync_redis

    from src.core.config import settings  # noqa: PLC0415

    try:
        # Dung sync redis client vi Celery worker khong co async event loop
        r_sync = sync_redis.from_url(settings.REDIS_URL)

        import json

        from src.core.sse import CHANNEL_ORG, CHANNEL_TASK  # noqa: PLC0415

        payload = json.dumps(
            {
                "event": "tags_updated",
                "task_id": task_id,
                "data": {"tag": tag, "confidence": round(confidence, 3)},
            }
        )
        r_sync.publish(CHANNEL_TASK.format(task_id=task_id), payload)
        r_sync.publish(CHANNEL_ORG.format(org_id=org_id), payload)
        r_sync.close()

        logger.info("nlp_sse_event_published", task_id=task_id, tag=tag)
    except Exception as e:
        # Publish that bai khong nen anh huong toi result chinh
        logger.warning("nlp_sse_publish_failed", task_id=task_id, error=str(e))
