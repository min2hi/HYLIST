FROM python:3.12-slim

# Thiết lập biến môi trường
# PYTHONPATH=/app dam bao ca src/ lan ml/ module deu importable
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=/app \
    PYTHONPATH=/app

WORKDIR $APP_HOME

# Cài đặt system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml truoc (cache busting layer)
# Build context = repo root, nen phai chi dinh duong dan day du
COPY backend/pyproject.toml ./

# Cài đặt Python dependencies
RUN pip install --no-cache-dir .[dev]

# Copy backend source code vao /app/
COPY backend/ .

# Copy ml/ module vao /app/ml/
# MLService.initialize() va TaskFeatureExtractor can import 'ml.features.task_extractor'
# PYTHONPATH=/app nen 'ml' resolve thanh /app/ml
COPY ml/ ./ml/

# Chạy bằng Uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
