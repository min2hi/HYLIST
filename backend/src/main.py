"""
FastAPI Application Entry Point.

Thứ tự khởi động:
  1. Setup logging (structlog)
  2. Sentry error tracking
  3. FastAPI app với middleware stack
  4. Prometheus metrics
  5. Register routers
  6. Health check endpoint
"""
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .core.config import settings
from .core.logging import get_logger, setup_logging
from .middleware.audit_log import AuditLogMiddleware
from .middleware.idempotency import IdempotencyMiddleware

# Setup logging trước tất cả
setup_logging()
logger = get_logger(__name__)

# Sentry error tracking
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=0.1,  # 10% traces (tránh spam)
    )
    logger.info("sentry_initialized", environment=settings.APP_ENV)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# ─── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="HYLIST API",
    description="Intelligent Task Orchestration System",
    version="1.0.0",
    docs_url="/docs" if settings.is_development else None,  # Ẩn Swagger trong production
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
)

# Rate limiter exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore

# ─── Middleware (thứ tự quan trọng — thực thi từ dưới lên) ───────────────────
# Thứ tự: CORS → Idempotency → AuditLog (outer → inner)
app.add_middleware(AuditLogMiddleware)       # Tuần 3: ghi log mọi thay đổi
app.add_middleware(IdempotencyMiddleware)    # Tuần 3: chống tạo trùng khi retry
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js dev
        "http://localhost:8000",   # API self
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Prometheus Metrics ───────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ─── Routers ──────────────────────────────────────────────────────────────────
# TODO Tuần 2: Import và register routers
from .api.v1 import auth, projects, tasks
app.include_router(auth.router,     prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(tasks.router,    prefix="/api/v1")


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """
    Health check endpoint.
    Docker / K8s dùng để kiểm tra app có sống không.
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.APP_ENV,
    }


@app.get("/", tags=["health"])
async def root() -> dict:
    return {"message": "HYLIST API is running", "docs": "/docs"}


# ─── Startup / Shutdown Events ────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event() -> None:
    logger.info(
        "app_starting",
        environment=settings.APP_ENV,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
    )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("app_shutting_down")
