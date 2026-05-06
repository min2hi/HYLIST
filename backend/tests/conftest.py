"""
conftest.py — Test fixtures.

Kiến trúc:
  - SQLite in-memory + StaticPool cho mọi tests.
  - Dùng override_engine() từ database.py — KHÔNG dùng os.environ DATABASE_URL trick.
  - setup_test_db (session-scope, autouse): tạo engine + tables 1 lần cho cả session.
  - clean_tables (function-scope, autouse): xóa data giữa các tests — không leak.
  - Unit tests: inject db_session trực tiếp vào Service.
  - Integration tests: client fixture, get_db đã được override qua override_engine().
"""

import asyncio
import os
from typing import AsyncGenerator

# Set trước khi import src — chỉ cần APP_ENV và SECRET_KEY
# DATABASE_URL không cần set ở đây vì dùng override_engine() thay thế
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


# ── Event Loop (session-scoped) ───────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ── Engine Setup (session-scoped, autouse) ────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db() -> AsyncGenerator[AsyncEngine, None]:
    """
    Khởi tạo SQLite engine và override app engine trước khi bất kỳ test nào chạy.

    Cách hoạt động:
      1. Tạo SQLite in-memory engine với StaticPool.
      2. Gọi override_engine() → app's get_db() sẽ dùng engine này.
      3. Tạo toàn bộ tables từ Base.metadata.
      4. Yield engine cho các fixture khác dùng.
      5. Sau session: drop tables, dispose engine.

    Ưu điểm so với env-var trick:
      - Không phụ thuộc thứ tự import.
      - Explicit và dễ hiểu.
      - Test có thể chạy subset mà không lo vỡ.
    """
    # Import sau khi env vars đã set
    from src.core.database import Base, override_engine

    engine = create_async_engine(
        SQLITE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Override app engine — từ đây get_db() dùng SQLite
    override_engine(engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Table Cleanup (function-scoped, autouse) ──────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def clean_tables(setup_test_db: AsyncEngine) -> AsyncGenerator[None, None]:
    """
    Xóa toàn bộ data sau mỗi test để đảm bảo test isolation.

    Xóa theo thứ tự ngược dependency (child trước, parent sau)
    để tránh vi phạm foreign key constraints.
    """
    yield
    from src.core.database import Base
    async with setup_test_db.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


# ── DB Session cho Unit Tests ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session(setup_test_db: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Session riêng biệt cho mỗi unit test — inject trực tiếp vào Service."""
    SessionLocal = async_sessionmaker(setup_test_db, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()


# ── HTTP Client cho Integration Tests ────────────────────────────────────────

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient gọi app qua ASGI transport.

    get_db() trong app đã được override bởi setup_test_db (qua override_engine),
    nên không cần dependency_overrides ở đây.
    """
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Shared Data Fixtures ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession):
    from src.models import Organization

    org = Organization(name="Test Corp", slug=f"test-{id(db_session)}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_org):
    from src.models import User, UserRole
    from src.core.security import hash_password

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
def test_user_token(test_user) -> str:
    from src.core.security import create_access_token

    return create_access_token(test_user.id, test_user.org_id, test_user.role)


@pytest.fixture
def auth_headers(test_user_token: str) -> dict:
    return {"Authorization": f"Bearer {test_user_token}"}
