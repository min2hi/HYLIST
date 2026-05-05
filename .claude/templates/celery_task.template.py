# celery_task.template.py — Celery Task Template
# ============================================================
# HƯỚNG DẪN:
#   1. Copy → đổi tên thành `<tên>_task.py` trong workers/
#   2. Tìm-Thay "example"/"Example" → tên task
#   3. Chọn queue phù hợp: "default" | "nlp" | "agent" | "monitor"
#   4. Xóa comment hướng dẫn (#*)
# ============================================================
# NGUYÊN TẮC:
#   ✅ Kiểm tra budget_guard trước mọi LLM call
#   ✅ Có time_limit và soft_time_limit
#   ✅ Retry với exponential backoff
#   ✅ Dead Letter Queue xử lý khi hết retry
#   ✅ Structured logging với task context
#   ❌ KHÔNG để task chạy vô thời hạn
# ============================================================

import asyncio
from celery.exceptions import SoftTimeLimitExceeded
import structlog

from ..core.celery_app import celery_app
from ..core.redis import redis_client

logger = structlog.get_logger()


@celery_app.task(
    bind=True,
    name="workers.example.run_example_task",   #* Đổi tên task
    queue="default",                            #* "default" | "nlp" | "agent" | "monitor"
    max_retries=3,
    time_limit=300,          #* Hard timeout 5 phút — task bị kill sau đây
    soft_time_limit=240,     #* Soft timeout 4 phút — raise SoftTimeLimitExceeded
    acks_late=True,          #* Chỉ ack sau khi task thành công (at-least-once delivery)
)
def run_example_task(self, record_id: str, user_id: str, **kwargs):  #* Đổi tên function
    """
    #* Mô tả task làm gì.
    #* Khi nào được trigger: ...
    """
    task_id = self.request.id
    logger.info("task_started", task_name="example", record_id=record_id, celery_task_id=task_id)

    try:
        #* [Nếu task gọi LLM] — BẮT BUỘC check budget trước
        # from ..workers.budget_guard import budget_guard
        # if not asyncio.run(budget_guard.can_execute(user_id)):
        #     logger.warning("budget_exceeded", user_id=user_id, record_id=record_id)
        #     self.apply_async(args=[record_id, user_id], countdown=86400)
        #     return {"status": "rescheduled", "reason": "budget_exceeded"}

        #* === LOGIC CHÍNH CỦA TASK ===
        result = do_work(record_id)  #* Thay bằng logic thật

        logger.info("task_completed", task_name="example", record_id=record_id, result=result)
        return {"status": "success", "result": result}

    except SoftTimeLimitExceeded:
        logger.warning("task_timeout", task_name="example", record_id=record_id)
        #* Xử lý timeout gracefully — tạo pending review thay vì crash
        asyncio.run(handle_timeout(record_id))
        return {"status": "timeout"}

    except Exception as exc:
        logger.error("task_failed", task_name="example", record_id=record_id, error=str(exc))
        #* Exponential backoff: 30s, 60s, 120s
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


def do_work(record_id: str):  #* Thay bằng logic thật
    """Logic chính — tách ra hàm riêng để dễ test."""
    pass


async def handle_timeout(record_id: str):
    """Xử lý khi task timeout — thông báo hoặc tạo pending review."""
    logger.warning("handling_timeout", record_id=record_id)
    #* Implement theo use case: notify user, create pending review, etc.


# =========================================================
# DEAD LETTER QUEUE HANDLER
# Đăng ký trong celery_app.py:
#   task_routes = {"workers.example.handle_dlq": {"queue": "dlq"}}
# =========================================================
@celery_app.task(name="workers.example.handle_dlq")  #* Đổi tên
def handle_dlq(record_id: str, error: str, original_task: str):
    """Xử lý tin nhắn đã fail hết số lần retry."""
    logger.error("dlq_received", record_id=record_id, error=error, original_task=original_task)
    #* Notify admin, tạo manual review record, v.v.


# =========================================================
# SCHEDULED TASK (Celery Beat) — bỏ comment nếu cần
# Đăng ký trong celery_app.py beat_schedule
# =========================================================
# @celery_app.task(name="workers.example.scheduled_job")
# def scheduled_example_job():
#     """Chạy theo lịch định kỳ."""
#     logger.info("scheduled_job_started", task_name="example")
#     # ... logic
