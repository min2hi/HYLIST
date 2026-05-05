"""
Celery App Configuration.
"""

from celery import Celery

from .config import settings

celery_app = Celery(
    "hylist_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["src.workers.ml_worker"],
)

# Cấu hình Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max
)
