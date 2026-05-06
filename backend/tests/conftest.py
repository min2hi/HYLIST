"""
conftest.py — Test fixtures.

Kiến trúc:
  - Dùng SQLite in-memory (StaticPool) độc lập hoàn toàn với app's engine.
  - Unit tests: inject db_session trực tiếp vào Service.
  - Integration tests: override get_db để dùng cùng SQLite engine đã có tables.
"""

import asyncio
import os
from typing import AsyncGenerator

# MUST set before importing anything from src
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from src.main import app
from src.core.database import Base, get_db
from src.core.security import hash_password, create_access_token
from src.models import Organization, User, UserRole

# ── Shared SQLite Engine dùng StaticPool ─────────────────────────────────────
# StaticPool buộc tất cả connections dùng chung 1 DB in-memory.
# Điều này đảm bảo unit test và integration test thấy cùng data.

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Session-scoped engine — tables tạo 1 lần, dùng xuyên suốt test session."""
    engine = create_async_engine(
        SQLITE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── DB Session cho Unit Tests ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Session riêng biệt cho mỗi unit test."""
    SessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()


# ── HTTP Client cho Integration Tests ────────────────────────────────────────

@pytest_asyncio.fixture
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient với app đã được override get_db → dùng cùng SQLite engine,
    đảm bảo integration tests không gặp 'no such table'.
    """
    SessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with SessionLocal() as session:
            async with session.begin():
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


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
