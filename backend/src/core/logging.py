"""
Structured logging setup với structlog.
Tại sao structlog thay vì print()?
  - Output JSON → searchable trong Grafana Loki
  - Tự động thêm context (timestamp, level, service)
  - Không cần thay đổi code khi đổi log destination
"""
import logging
import sys
import structlog
from .config import settings


def setup_logging() -> None:
    """Gọi 1 lần khi app startup."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Cấu hình standard logging (cho thư viện bên ngoài)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Cấu hình structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        # Production: JSON format → Loki, ELK
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Development: màu sắc dễ đọc
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """Lấy logger có context.
    
    Dùng:
        logger = get_logger(__name__)
        logger.info("task_created", task_id=str(task.id), org_id=str(user.org_id))
    
    KHÔNG dùng:
        print(f"Task created: {task.id}")
    """
    return structlog.get_logger(name)
