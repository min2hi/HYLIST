# Dockerfile — API + ML Worker container (lean, khong co PyTorch)
#
# Strategy: Tach deps thanh 3 layers rieng biet de:
#   1. Tan dung Docker layer cache tot nhat
#   2. Tranh OOM khi install tat ca cung luc
#   3. Build nhanh hon khi chi thay doi src code
#
# Layer order (from slowest to change → fastest to change):
#   1. System deps   (thay doi khi them apt package)
#   2. Core Python   (thay doi khi bump pydantic, fastapi...)
#   3. ML/Heavy deps (thay doi khi bump onnxruntime, shap...)
#   4. Dev/test deps (thay doi khi them pytest plugin...)
#   5. Source code   (thay doi moi commit)

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=/app \
    PYTHONPATH=/app \
    # Giam memory usage cua pip resolver
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR $APP_HOME

# ── Layer 1: System deps (hiem khi thay doi) ──────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Layer 2: Copy manifest (trigger cho layers tiep theo) ─────────────────────
COPY backend/pyproject.toml ./

# ── Layer 3: Core API deps (FastAPI, SQLAlchemy, Redis, Celery, Auth...) ──────
# Tach rieng de khi ML deps thay doi khong phai reinstall fastapi
RUN pip install \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.30.0" \
    "sqlalchemy>=2.0.0" \
    "asyncpg>=0.29.0" \
    "alembic>=1.13.0" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.2.0" \
    "python-jose[cryptography]>=3.3.0" \
    "passlib[bcrypt]>=1.7.4" \
    "python-multipart>=0.0.9" \
    "redis[hiredis]>=5.0.0" \
    "celery>=5.4.0" \
    "sse-starlette>=2.1.0" \
    "structlog>=24.2.0" \
    "sentry-sdk[fastapi]>=2.5.0" \
    "slowapi>=0.1.9" \
    "prometheus-fastapi-instrumentator>=7.0.0" \
    "httpx>=0.27.0" \
    "aiofiles>=23.2.0" \
    "python-dotenv>=1.0.0"

# ── Layer 4: ML inference deps (nang hon nhung it thay doi) ───────────────────
# Cai rieng de tranh OOM khi cai tat ca cung luc voi Core deps
# --no-build-isolation de tranh pip resolver OOM voi shap
RUN pip install \
    "numpy>=1.26.0" \
    "pandas>=2.2.0" \
    "onnxruntime>=1.18.0" && \
    pip install "shap>=0.45.0" --no-build-isolation

# ── Layer 5: Dev/test deps (chi can trong dev/CI, khong anh huong runtime) ────
# NOTE: neu muon prod image nhe hon, tach thanh 2 build stages
RUN pip install \
    "pytest>=8.2.0" \
    "pytest-asyncio>=0.23.0" \
    "pytest-cov>=5.0.0" \
    "aiosqlite>=0.20.0" \
    "httpx>=0.27.0" \
    "anyio>=4.0.0" \
    "ruff>=0.4.0" \
    "bandit>=1.7.0" \
    "mypy>=1.10.0"

# ── Layer 6: Source code (thay doi moi commit — PHAI la layer cuoi) ───────────
COPY backend/ .
COPY ml/ ./ml/

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
