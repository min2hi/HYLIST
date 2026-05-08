"""
FastAPI Application Entry Point.

Thứ tự khởi động:
  1. Setup logging (structlog)
  2. Sentry error tracking
  3. FastAPI app với lifespan context manager (chuẩn mới FastAPI 0.93+)
  4. Middleware stack
  5. Prometheus metrics
  6. Register routers
  7. Health check endpoint (kiểm tra DB + Redis thật sự)
"""

import asyncio
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .core.config import settings
from .core.errors import register_exception_handlers
from .core.logging import get_logger, setup_logging
from .middleware.audit_log import AuditLogMiddleware
from .middleware.idempotency import IdempotencyMiddleware

# Setup logging trước tất cả
setup_logging()
logger = get_logger(__name__)

# ─── Custom Business Metrics (Prometheus) ────────────────────────────────────
# Default FastAPI metrics: request count + latency (per endpoint)
# Business metrics: domain-specific signals for alerting
TASKS_CREATED = Counter(
    "hylist_tasks_created_total",
    "Total tasks created",
    ["org_id"],  # Label: theo doi per-org
)
ML_PREDICTION_LATENCY = Histogram(
    "hylist_ml_prediction_seconds",
    "ML prediction latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)
NLP_QUEUE_DEPTH = Gauge(
    "hylist_nlp_queue_depth",
    "Number of pending NLP tagging tasks",
)
SSE_CONNECTIONS = Gauge(
    "hylist_sse_connections_active",
    "Number of active SSE connections",
)

# Sentry error tracking
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=0.1,
    )
    logger.info("sentry_initialized", environment=settings.APP_ENV)


# ─── Lifespan (chuẩn mới thay thế on_event) ──────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Quản lý vòng đời ứng dụng theo chuẩn FastAPI 0.93+.
    Code trước yield = startup. Code sau yield = shutdown.
    """
    logger.info(
        "app_starting",
        environment=settings.APP_ENV,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
    )

    # 1. Initialize SSE EventBus (Redis Pub/Sub bridge)
    from .core.redis import redis_client
    from .core.sse import SSEEventBus

    bus = SSEEventBus.init(redis_client)
    await bus.start()
    logger.info("sse_event_bus_ready")

    # 2. Load ONNX model vao memory (graceful fallback neu model chua co)
    from .services.ml_service import ml_service

    ml_service.initialize()

    yield

    # Shutdown: stop SSE bus truoc, roi dispose DB pool
    logger.info("app_shutting_down")
    await bus.stop()
    from .core.database import get_engine

    await get_engine().dispose()


# ─── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="HYLIST API",
    description="Intelligent Task Orchestration System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)
# Rate limiter exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore

# RFC 7807 Problem Details — override default {"detail": "..."} error format
# Dung boi: Stripe, GitHub, Shopify — client code check 'type' URI
register_exception_handlers(app)

# ─── Middleware (thứ tự quan trọng — thực thi từ dưới lên theo Starlette) ────
# Request flow: CORS → Idempotency → AuditLog → Router
app.add_middleware(AuditLogMiddleware)  # Tuần 3: persist mọi state change vào audit_logs
app.add_middleware(IdempotencyMiddleware)  # Tuần 3: chống tạo trùng khi client retry
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev
        "http://localhost:8000",  # API self
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ─── Prometheus Metrics ───────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ─── Routers ──────────────────────────────────────────────────────────────────
from .api.v1 import auth, events, ml, projects, tasks  # noqa: E402

app.include_router(auth.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(ml.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")


# ─── Health Check (Kiểm tra thật sự — không trả static response) ─────────────
@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """
    Health check endpoint cho Load Balancer / K8s liveness probe.

    Kiểm tra:
      - PostgreSQL: SELECT 1
      - Redis: PING

    Trả về 200 nếu tất cả healthy.
    Trả về 503 nếu bất kỳ dependency nào fail.
    """
    from fastapi import status
    from fastapi.responses import JSONResponse

    from .core.database import engine
    from .core.redis import redis_client

    db_ok = False
    redis_ok = False
    errors: list[str] = []

    # Check PostgreSQL
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        errors.append(f"postgres: {e!s}")
        logger.error("health_check_db_failed", error=str(e))

    # Check Redis
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=2.0)
        redis_ok = True
    except Exception as e:
        errors.append(f"redis: {e!s}")
        logger.error("health_check_redis_failed", error=str(e))

    all_healthy = db_ok and redis_ok
    payload = {
        "status": "healthy" if all_healthy else "degraded",
        "version": "1.0.0",
        "environment": settings.APP_ENV,
        "checks": {
            "postgres": "ok" if db_ok else "fail",
            "redis": "ok" if redis_ok else "fail",
        },
    }

    if not all_healthy:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)
    return payload


@app.get("/", tags=["health"])
async def root() -> dict:
    return {"message": "HYLIST API is running", "docs": "/docs"}
