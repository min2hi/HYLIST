# Dockerfile — API + ML Worker (lean image, khong co PyTorch)
#
# ┌─────────────────────────────────────────────────────────────────┐
# │  Professional multi-stage build voi uv                         │
# │                                                                 │
# │  Stage 1 (builder): Install tat ca deps vao /app/.venv          │
# │  Stage 2 (runtime): Copy .venv tu builder, khong co build tools │
# │                                                                 │
# │  Ket qua:                                                       │
# │   - Final image khong co uv, pip, build-essential, gcc          │
# │   - Final image nho hon ~200MB so voi single-stage              │
# │   - Layer cache hieu qua: chi rebuild khi uv.lock thay doi      │
# └─────────────────────────────────────────────────────────────────┘

# ─── Stage 1: Dependency installer ────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Cai uv tu official image (khong phua pip install uv)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# System deps cho compile C extensions (shap, asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy lockfile TRUOC source code
# → Docker cache hit khi chi doi code ma khong doi deps
COPY backend/pyproject.toml backend/uv.lock ./

# Install chi core + ml group (KHONG co nlp, training, agent)
# --frozen: doc thang tu uv.lock, khong resolve lai → nhanh + deterministic
# --no-install-project: chi install deps, khong cai package hylist-backend
# (source code chua duoc copy, se copy sau)
RUN uv sync \
    --frozen \
    --no-install-project \
    --no-group dev \
    --no-group nlp \
    --no-group training \
    --no-group agent \
    --group ml

# Copy source code (layer cuoi cung — thay doi moi commit)
COPY backend/ .
COPY ml/ ./ml/

# Install project itself (src/ vao .venv)
RUN uv sync \
    --frozen \
    --no-group dev \
    --no-group nlp \
    --no-group training \
    --no-group agent \
    --group ml

# ─── Stage 2: Runtime image ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Chi can libpq runtime (khong can build-essential, gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    # Dung .venv tu builder, khong dung system Python
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Chi copy .venv da cai xong tu builder (khong co uv, pip, gcc)
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src ./src
COPY --from=builder /app/ml ./ml
COPY --from=builder /app/alembic.ini ./
COPY --from=builder /app/alembic ./alembic

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
