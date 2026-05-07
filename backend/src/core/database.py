"""
Database session management với SQLAlchemy 2.0 async.

Pattern quan trọng:
  - Lazy engine creation: engine KHÔNG tạo khi import, chỉ tạo khi lần đầu cần.
    → test có thể override engine trước khi app dùng nó.
  - override_engine(): dành riêng cho test — thay thế engine mà không cần env-var tricks.
  - session.begin(): auto-commit khi thành công, auto-rollback khi exception.
  - KHÔNG gọi session.commit() trong service — context manager lo.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from .config import settings


class Base(DeclarativeBase):
    """Base class cho tất cả SQLAlchemy models."""

    pass


# ── Lazy singletons — None cho đến khi lần đầu được dùng ───────────────────
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def _create_engine(url: str) -> AsyncEngine:
    """
    Tạo engine phù hợp với database dialect.

    - SQLite  : StaticPool (buộc dùng chung 1 connection in-memory, dành cho test).
    - PostgreSQL: Connection pool đầy đủ với pre-ping và recycle.
    """
    if "sqlite" in url:
        return create_async_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_async_engine(
        url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,  # tự reconnect nếu DB restart
        pool_recycle=3600,  # recycle connection sau 1 giờ
        echo=settings.is_development,
    )


def get_engine() -> AsyncEngine:
    """Lấy engine hiện tại, tạo mới nếu chưa có."""
    global _engine
    if _engine is None:
        _engine = _create_engine(settings.DATABASE_URL)
    return _engine


def get_session_factory() -> async_sessionmaker:
    """Lấy session factory hiện tại, tạo mới nếu chưa có."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,  # Giữ object valid sau commit
        )
    return _session_factory


def override_engine(engine: AsyncEngine) -> None:
    """
    Override engine và session factory.

    CHỈ dùng trong test — cho phép test inject SQLite engine mà không cần
    env-var tricks hay import ordering hacks.

    Dùng trong conftest.py:
        override_engine(create_async_engine("sqlite+aiosqlite:///:memory:", ...))
    """
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency — inject vào Router.

    Session lifecycle:
      1. Lấy session từ factory (lazy-initialized)
      2. Bắt đầu transaction
      3. yield session cho request handler
      4. Nếu không có exception → commit tự động
      5. Nếu có exception → rollback tự động
      6. Đóng session

    Dùng:
        @router.get("/tasks")
        async def get_tasks(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_session_factory()() as session:
        async with session.begin():
            try:
                yield session
            except Exception:
                await session.rollback()
                raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager cho DB session — dùng trong Celery worker.

    Celery task không có FastAPI Depends, cần tự quản lý session.
    Pattern này mirror get_db() nhưng dùng được trong sýc context thường.

    Dùng:
        async with get_db_context() as db:
            db.add(record)
            await db.commit()
    """
    async with get_session_factory()() as session:
        async with session.begin():
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
