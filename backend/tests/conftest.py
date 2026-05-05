"""
conftest.py — Test fixtures.

Kiến trúc:
  - Unit tests (test_auth_service): inject db_session trực tiếp vào Service
  - Integration tests (test_auth_api): dùng HTTP client, app tự quản lý DB session
"""
import asyncio
import os
from typing import AsyncGenerator

# MUST set before importing anything from src
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.main import app
from src.core.database import Base, get_db
from src.core.security import hash_password, create_access_token
from src.models import Organization, User, UserRole

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://hylist:hylist_password@localhost:5433/hylist_db"
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ── Engine cho Unit Tests (inject vào service trực tiếp) ─────────────────────

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Session riêng biệt cho mỗi unit test."""
    SessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()


# ── HTTP Client cho Integration Tests (app tự quản lý connection) ─────────────

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient gọi app qua ASGI transport.
    App dùng connection pool riêng — không xung đột với unit test session.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Shared Data Fixtures ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession) -> Organization:
    org = Organization(name="Test Corp", slug=f"test-{id(db_session)}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_org: Organization) -> User:
    user = User(
        org_id=test_org.id,
        email=f"admin-{id(db_session)}@example.com",
        hashed_password=hash_password("test_password_123"),
        full_name="Test Admin",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def test_user_token(test_user: User) -> str:
    return create_access_token(test_user.id, test_user.org_id, test_user.role)


@pytest.fixture
def auth_headers(test_user_token: str) -> dict:
    return {"Authorization": f"Bearer {test_user_token}"}
