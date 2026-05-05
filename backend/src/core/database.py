"""
Database session management với SQLAlchemy 2.0 async.

Pattern quan trọng:
  - Connection pool: tái sử dụng connections, không tạo mới mỗi request
  - pool_pre_ping=True: tự reconnect nếu DB restart
  - session.begin(): auto-commit khi thành công, auto-rollback khi exception
  - KHÔNG gọi session.commit() trong service — context manager lo
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings
from sqlalchemy.pool import NullPool

# Setup engine arguments, exclude pool arguments for sqlite
engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
    "echo": settings.is_development,
}

if "sqlite" not in settings.DATABASE_URL:
    engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
else:
    engine_kwargs["poolclass"] = NullPool
    # Remove unsupported arguments for NullPool
    engine_kwargs.pop("pool_pre_ping", None)
    engine_kwargs.pop("pool_recycle", None)

# Engine: quản lý connection pool đến DB
engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,  # Giữ object valid sau commit
)


class Base(DeclarativeBase):
    """Base class cho tất cả SQLAlchemy models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency — inject vào Router.

    Session lifecycle:
      1. Tạo session
      2. Bắt đầu transaction (session.begin())
      3. yield session cho request handler
      4. Nếu không có exception → commit tự động
      5. Nếu có exception → rollback tự động
      6. Đóng session

    Dùng:
        @router.get("/tasks")
        async def get_tasks(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
