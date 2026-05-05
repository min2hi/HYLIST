"""
Alembic environment — cấu hình migration runner.

Quan trọng:
  - Import tất cả models trước khi gọi autogenerate
  - Dùng psycopg2 (sync) cho Alembic, asyncpg cho runtime
  - Filter migrations theo org_id (multi-tenancy) nếu cần
"""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Import tất cả models để autogenerate phát hiện thay đổi
from src.models import Base  # noqa: F401 — import required for autogenerate

# Alembic Config object
config = context.config

# Override connection string từ environment variable
database_url = os.environ.get("DATABASE_URL", "")
if database_url.startswith("postgresql+asyncpg"):
    # Alembic cần psycopg2 (sync), không phải asyncpg
    database_url = database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Logging setup
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata cho autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Chạy migration mà không cần kết nối DB thực."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Chạy migration với kết nối DB thực."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
