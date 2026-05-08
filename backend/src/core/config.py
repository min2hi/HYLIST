"""
App settings — đọc từ .env file.
Tất cả config đi qua đây, không hardcode ở nơi khác.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ─── App ──────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    SECRET_KEY: str = "change-me-in-production"
    LOG_LEVEL: str = "INFO"
    # CORS_ORIGINS: comma-separated list, e.g. "http://localhost:3000,https://app.hylist.io"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    # ─── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://hylist:hylist_password@localhost:5433/hylist_db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ─── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ─── Celery ───────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # ─── Auth ─────────────────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── ML ───────────────────────────────────────────────────────────────────
    MLFLOW_TRACKING_URI: str = "http://localhost:5001"
    ONNX_MODEL_PATH: str = "ml/models/predictor_latest.onnx"
    DRIFT_THRESHOLD_MAE: float = 2.0
    SHADOW_MODE_ENABLED: bool = True

    # ─── LLM / Agent ──────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_DAILY_BUDGET_USD: float = 10.0
    HITL_CONFIDENCE_THRESHOLD: float = 0.95

    # ─── Observability ────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""
    PROMETHEUS_PORT: int = 9090

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV == "test"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS env var thành list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


def get_settings() -> Settings:
    """Load settings từ env. Không cache để test có thể override env vars."""
    return Settings()


# Singleton dùng trong toàn app (cache thủ công)
settings = get_settings()
