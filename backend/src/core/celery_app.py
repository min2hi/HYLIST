"""
Celery Application Configuration.

Queue routing:
  ml      → hylist-worker   (Dockerfile lean: ONNX inference)
  nlp     → hylist-nlp      (Dockerfile.nlp fat: PyTorch + SetFit)
  default → hylist-worker   (tasks khong chi dinh queue)

Scale doc lap:
  docker compose scale hylist-worker=2   # them ML workers
  docker compose scale hylist-nlp=1      # NLP worker dung 1 (PyTorch lon)
"""

from celery import Celery

from .config import settings

celery_app = Celery(
    "hylist_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "src.workers.ml_worker",  # Queue: ml
        "src.workers.nlp_worker",  # Queue: nlp (chi chay trong Dockerfile.nlp container)
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    # Monitoring
    task_track_started=True,
    # Limits
    task_time_limit=300,  # 5 phut max per task
    task_soft_time_limit=240,  # 4 phut: raise SoftTimeLimitExceeded truoc khi hard kill
    # Queue routing — default queue cho tasks khong co queue= chi dinh
    task_default_queue="default",
    task_routes={
        "ml.*": {"queue": "ml"},
        "nlp.*": {"queue": "nlp"},
    },
    # Worker optimizations
    worker_prefetch_multiplier=1,  # Moi worker chi lay 1 task truoc (tranh starve NLP)
    task_acks_late=True,  # Chi ACK sau khi task hoan thanh (an toan hon)
)
