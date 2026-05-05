# Testing Rules — HYLIST

> **Stack:** pytest + pytest-asyncio + httpx + Testcontainers + schemathesis + factory-boy
> **Đọc khi:** viết test, mock data, fixtures

---

## Test Pyramid

```
schemathesis        ← Contract tests: auto-test mọi endpoint theo openapi.yaml
  ↑ ít nhất
Integration tests   ← FastAPI endpoints + PostgreSQL thật (Testcontainers)
  ↑
Unit tests          ← Service logic, utilities (isolated, fast)
  ↑ nhiều nhất
ML Parity tests     ← FeatureExtractor: ORM vs dict phải cho kết quả giống nhau
```

**CI Gate:** `pytest --cov=src --cov-fail-under=70` — block merge nếu coverage < 70%

---

## Naming Convention

```
backend/src/services/task.service.py         → backend/tests/unit/test_task_service.py
backend/src/api/v1/tasks.py                  → backend/tests/integration/test_task_api.py
ml/features/task_extractor.py                → backend/tests/ml/test_feature_extractor.py
```

---

## conftest.py — Shared Fixtures (BẮT BUỘC)

```python
# backend/tests/conftest.py
import pytest
import asyncio
from httpx import AsyncClient
from testcontainers.postgres import PostgresContainer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# PostgreSQL thật — KHÔNG SQLite (SQLite không support JSONB, UUID, ARRAY)
@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:17") as pg:  # Khớp với PG17 đang cài local
        yield pg

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_session(postgres_container):
    engine = create_async_engine(
        postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_sessionmaker(engine)() as session:
        yield session
        await session.rollback()  # Cleanup sau mỗi test

@pytest.fixture
async def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

# Auth fixtures
@pytest.fixture
def admin_user():
    return CurrentUser(id=uuid4(), org_id=uuid4(), role=Role.ADMIN, email="admin@test.com")

@pytest.fixture
def member_user(admin_user):
    return CurrentUser(id=uuid4(), org_id=admin_user.org_id, role=Role.MEMBER, email="member@test.com")

@pytest.fixture
async def admin_headers(client, admin_user):
    # Login và lấy JWT thật
    resp = await client.post("/api/v1/auth/login", json={"email": "admin@test.com", "password": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
```

---

## Unit Test Pattern

```python
# backend/tests/unit/test_task_service.py
import pytest
from unittest.mock import AsyncMock, patch

class TestTaskService:

    async def test_create_task_success(self, db_session, member_user):
        service = TaskService(db_session)
        dto = CreateTaskDto(title="Write unit tests", priority=2, estimated_hours=3.0)

        result = await service.create(dto, member_user)

        assert result.title == "Write unit tests"
        assert result.org_id == member_user.org_id      # Multi-tenancy check
        assert result.created_by == member_user.id       # Ownership check

    async def test_create_task_empty_title_raises(self, db_session, member_user):
        with pytest.raises(ValueError, match="Title không được để trống"):
            await TaskService(db_session).create(
                CreateTaskDto(title="  "), member_user
            )

    async def test_get_task_cross_org_raises(self, db_session, member_user):
        """Đảm bảo IDOR protection — không thể get task của org khác."""
        other_org_task = TaskFactory(org_id=uuid4())  # Khác org
        db_session.add(other_org_task)
        await db_session.flush()

        with pytest.raises(ValueError, match="Không tìm thấy"):
            await TaskService(db_session).get_by_id(other_org_task.id, member_user)

    async def test_nlp_task_enqueued_on_create(self, db_session, member_user):
        """NLP tagging phải được trigger sau khi tạo task."""
        with patch("backend.src.workers.nlp_tasks.enqueue_nlp_tagging") as mock_enqueue:
            await TaskService(db_session).create(
                CreateTaskDto(title="Bug in login"), member_user
            )
            mock_enqueue.delay.assert_called_once()
```

---

## Integration Test Pattern

```python
# backend/tests/integration/test_task_api.py
class TestTaskAPI:

    async def test_create_task_requires_auth(self, client):
        resp = await client.post("/api/v1/tasks/", json={"title": "Test"})
        assert resp.status_code == 401

    async def test_create_task_idempotency(self, client, admin_headers):
        """Same Idempotency-Key → same response, không tạo duplicate."""
        headers = {**admin_headers, "Idempotency-Key": "test-idem-123"}
        resp1 = await client.post("/api/v1/tasks/", json={"title": "T"}, headers=headers)
        resp2 = await client.post("/api/v1/tasks/", json={"title": "T"}, headers=headers)

        assert resp1.status_code == 201
        assert resp2.status_code == 200  # From cache
        assert resp1.json()["data"]["id"] == resp2.json()["data"]["id"]

    async def test_viewer_cannot_create_task(self, client, viewer_headers):
        resp = await client.post("/api/v1/tasks/", json={"title": "T"}, headers=viewer_headers)
        assert resp.status_code == 403

    async def test_admin_can_delete_task(self, client, admin_headers, seed_task):
        resp = await client.delete(f"/api/v1/tasks/{seed_task.id}", headers=admin_headers)
        assert resp.status_code == 200
        # Verify soft delete
        task = await db.get(Task, seed_task.id)
        assert task.deleted_at is not None

    async def test_response_format(self, client, admin_headers):
        """Mọi response phải có format { success, data }."""
        resp = await client.get("/api/v1/tasks/", headers=admin_headers)
        body = resp.json()
        assert "success" in body
        assert "data" in body
        assert body["success"] is True
```

---

## ML Parity Tests (BẮT BUỘC — Phase 2)

```python
# backend/tests/ml/test_feature_extractor.py
class TestFeatureExtractorParity:
    """
    ⚠️ CỰC KỲ QUAN TRỌNG: Training path và Serving path phải cho kết quả GIỐNG HỆT NHAU.
    Nếu test này fail → Training-Serving Skew → predictions sẽ sai trong production.
    """

    def test_orm_vs_dict_gives_identical_features(self, sample_task_orm, sample_task_dict):
        extractor = TaskFeatureExtractor()
        orm_features  = extractor.extract(sample_task_orm)   # Serving path (ORM)
        dict_features = extractor.extract(sample_task_dict)  # Training path (dict)

        assert orm_features == dict_features, \
            f"TRAINING-SERVING SKEW DETECTED!\n" \
            f"ORM: {orm_features}\nDict: {dict_features}"

    def test_all_required_features_present(self, sample_task):
        required = [
            "title_len", "desc_tokens", "priority_score", "has_deadline",
            "dependency_count", "subtask_count", "deadline_buffer_hrs",
            "assignee_workload", "revision_count", "created_dow",
        ]
        features = TaskFeatureExtractor().extract(sample_task)
        for f in required:
            assert f in features, f"Feature '{f}' missing from extractor!"

    def test_no_nan_in_features(self, sample_task):
        features = TaskFeatureExtractor().extract(sample_task)
        for key, val in features.items():
            assert val is not None and val == val, f"NaN detected in feature '{key}'"
```

---

## Factory Functions (KHÔNG hardcode test data)

```python
# backend/tests/factories.py
import factory
from factory import LazyFunction, Faker
import uuid

class TaskFactory(factory.Factory):
    class Meta:
        model = dict   # Hoặc Task ORM class

    id                   = LazyFunction(lambda: str(uuid.uuid4()))
    org_id               = LazyFunction(lambda: str(uuid.uuid4()))
    created_by           = LazyFunction(lambda: str(uuid.uuid4()))
    title                = Faker("sentence", nb_words=4)
    description          = Faker("paragraph")
    priority_score       = Faker("random_int", min=1, max=5)
    estimated_time       = Faker("pyfloat", min_value=0.5, max_value=40)
    assignee_workload    = Faker("pyfloat", min_value=0.0, max_value=1.0)
    dependency_count     = Faker("random_int", min=0, max=5)
    status               = "todo"
    tags                 = []

# Dùng:
task = TaskFactory()
tasks = TaskFactory.build_batch(50)   # 50 tasks cho mock data tests
```

---

## CI Commands

```bash
# Chạy toàn bộ test suite
pytest backend/tests/ --cov=backend/src --cov-report=xml --cov-fail-under=70 -v

# Chỉ unit tests (nhanh)
pytest backend/tests/unit/ -v

# ML parity tests (chạy sau khi đổi FeatureExtractor)
pytest backend/tests/ml/ -v

# Contract tests (chạy sau khi đổi openapi.yaml)
schemathesis run --checks all openapi.yaml --base-url http://localhost:8000
```

---

## Self-Check

```
[ ] Testcontainers PostgreSQL 17 (KHÔNG SQLite — không support JSONB, UUID, ARRAY)
[ ] conftest.py có session.rollback() sau mỗi test
[ ] ML parity test: ORM extract == dict extract (không có skew)
[ ] RBAC test: 403 khi sai role
[ ] Idempotency test: duplicate request không tạo thêm record
[ ] IDOR test: không thể get/update resource của org khác
[ ] Factory functions thay vì hardcoded data
[ ] Coverage >= 70% trước khi commit
[ ] Contract test với schemathesis sau khi đổi openapi.yaml
[ ] KHÔNG skip test mà không có lý do rõ ràng
```
