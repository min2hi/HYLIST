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

# Engine: quản lý connection pool đến PostgreSQL
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,          # Số connections giữ sẵn
    max_overflow=settings.DB_MAX_OVERFLOW,     # Cho phép tạo thêm khi cần
    pool_pre_ping=True,                        # Ping DB trước khi dùng connection
    pool_recycle=3600,                         # Recycle connection sau 1 giờ
    echo=settings.is_development,             # Log SQL queries khi dev
)

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
