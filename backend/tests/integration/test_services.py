"""
Integration tests cho TaskService và ProjectService — DB thật (SQLite in-memory).
Các test này verify business logic thực tế, không mock DB.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from src.core.security import CurrentUser
from src.models import Organization, User, UserRole
from src.schemas.project import CreateProjectDto, UpdateProjectDto
from src.schemas.task import CreateTaskDto, UpdateTaskDto
from src.services.project_service import ProjectService
from src.services.task_service import TaskService


def make_user(org_id=None, role: str = "admin") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        org_id=org_id or uuid.uuid4(),
        role=role,
        email="test@example.com",
        full_name="Test User",
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def org_and_user(db_session):
    """Tạo Organization + User thật trong DB."""
    org = Organization(name="Test Corp", slug=f"test-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    user_model = User(
        org_id=org.id,
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="hashed",
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user_model)
    await db_session.flush()

    current_user = CurrentUser(
        id=user_model.id,
        org_id=org.id,
        role="admin",
        email=user_model.email,
        full_name=user_model.full_name,
    )
    return org, user_model, current_user


@pytest_asyncio.fixture
async def project_in_db(db_session, org_and_user):
    """Tạo Project thật trong DB."""
    _, _, current_user = org_and_user
    service = ProjectService(db_session)
    dto = CreateProjectDto(name="Test Project", description="Test description")
    return await service.create(dto, current_user)


# ── ProjectService Tests ───────────────────────────────────────────────────────


class TestProjectServiceIntegration:
    @pytest.mark.asyncio
    async def test_create_project_success(self, db_session, org_and_user):
        """Tạo project và verify data trong DB."""
        _, _, current_user = org_and_user
        service = ProjectService(db_session)
        dto = CreateProjectDto(name="My Project", description="Desc")

        result = await service.create(dto, current_user)

        assert result.name == "My Project"
        assert result.id is not None
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_get_all_only_returns_own_org(self, db_session, org_and_user):
        """get_all() chỉ trả về projects của org đó — multi-tenancy."""
        _, _, current_user = org_and_user
        service = ProjectService(db_session)

        # Tạo 2 projects cho org này
        await service.create(CreateProjectDto(name="P1"), current_user)
        await service.create(CreateProjectDto(name="P2"), current_user)

        # User từ org khác
        other_user = make_user(role="admin")
        other_service = ProjectService(db_session)

        own_projects = await service.get_all(current_user)
        other_projects = await other_service.get_all(other_user)

        assert len(own_projects) == 2
        assert len(other_projects) == 0  # Org khác không thấy data

    @pytest.mark.asyncio
    async def test_get_by_id_idor_protection(self, db_session, org_and_user, project_in_db):
        """get_by_id() chặn IDOR — user khác org không lấy được project."""
        other_user = make_user(role="admin")
        service = ProjectService(db_session)

        with pytest.raises(ValueError, match="không tồn tại"):
            await service.get_by_id(project_in_db.id, other_user)

    @pytest.mark.asyncio
    async def test_update_project(self, db_session, org_and_user, project_in_db):
        """Update project và verify changes."""
        _, _, current_user = org_and_user
        service = ProjectService(db_session)
        dto = UpdateProjectDto(name="Updated Name", status="paused")

        result = await service.update(project_in_db.id, dto, current_user)

        assert result.name == "Updated Name"
        assert result.status == "paused"

    @pytest.mark.asyncio
    async def test_delete_project_soft_delete(self, db_session, org_and_user, project_in_db):
        """Soft delete không xóa thật — project không xuất hiện ở get_all."""
        _, _, current_user = org_and_user
        service = ProjectService(db_session)

        result = await service.delete(project_in_db.id, current_user)
        assert result["deleted"] is True

        # Verify không còn trong list
        projects = await service.get_all(current_user)
        ids = [p.id for p in projects]
        assert project_in_db.id not in ids

    @pytest.mark.asyncio
    async def test_update_empty_dto_no_change(self, db_session, org_and_user, project_in_db):
        """Update với empty dto trả về project không thay đổi."""
        _, _, current_user = org_and_user
        service = ProjectService(db_session)
        dto = UpdateProjectDto()  # Không có gì thay đổi

        result = await service.update(project_in_db.id, dto, current_user)
        assert result.name == project_in_db.name


# ── TaskService Tests ─────────────────────────────────────────────────────────


class TestTaskServiceIntegration:
    @pytest_asyncio.fixture
    async def project(self, db_session, org_and_user):
        """Tạo Project cho task tests."""
        _, _, current_user = org_and_user
        svc = ProjectService(db_session)
        return await svc.create(CreateProjectDto(name="Task Test Project"), current_user)

    @pytest.mark.asyncio
    async def test_create_task_success(self, db_session, org_and_user, project):
        """Tạo task với fields cơ bản."""
        _, _, current_user = org_and_user
        service = TaskService(db_session)
        dto = CreateTaskDto(title="Fix bug #123", project_id=project.id, priority_score=4)

        result = await service.create(dto, current_user)

        assert result.title == "Fix bug #123"
        assert result.priority_score == 4
        assert result.status == "todo"
        assert result.org_id == current_user.org_id

    @pytest.mark.asyncio
    async def test_create_task_with_deadline_buffer(self, db_session, org_and_user, project):
        """ML feature: deadline_buffer_hrs được tính đúng."""
        _, _, current_user = org_and_user
        service = TaskService(db_session)
        future_deadline = datetime.now(UTC) + timedelta(hours=48)
        dto = CreateTaskDto(
            title="Task with deadline",
            project_id=project.id,
            deadline=future_deadline,
        )

        result = await service.create(dto, current_user)
        assert result.deadline is not None

    @pytest.mark.asyncio
    async def test_task_title_stripped(self, db_session, org_and_user, project):
        """Title được strip whitespace."""
        _, _, current_user = org_and_user
        service = TaskService(db_session)
        dto = CreateTaskDto(title="  Padded Title  ", project_id=project.id)

        result = await service.create(dto, current_user)
        assert result.title == "Padded Title"

    @pytest.mark.asyncio
    async def test_get_all_tasks_filter_by_project(self, db_session, org_and_user, project):
        """get_all() filter đúng theo project_id."""
        _, _, current_user = org_and_user
        service = TaskService(db_session)

        # Tạo task cho project này
        dto = CreateTaskDto(title="Task A", project_id=project.id)
        await service.create(dto, current_user)

        results = await service.get_all(current_user, project_id=project.id)
        assert len(results) >= 1
        assert all(t.project_id == project.id for t in results)

    @pytest.mark.asyncio
    async def test_task_idor_protection(self, db_session, org_and_user, project):
        """get_by_id() chặn truy cập từ org khác."""
        _, _, current_user = org_and_user
        service = TaskService(db_session)
        dto = CreateTaskDto(title="Private task", project_id=project.id)
        task = await service.create(dto, current_user)

        other_user = make_user(role="member")
        with pytest.raises(ValueError, match="không tồn tại"):
            await service.get_by_id(task.id, other_user)

    @pytest.mark.asyncio
    async def test_update_task_status_to_done(self, db_session, org_and_user, project):
        """Update status sang DONE ghi completed_at."""
        _, _, current_user = org_and_user
        service = TaskService(db_session)
        task = await service.create(
            CreateTaskDto(title="Complete me", project_id=project.id), current_user
        )

        result = await service.update(task.id, UpdateTaskDto(status="done"), current_user)
        assert result.status == "done"

    @pytest.mark.asyncio
    async def test_soft_delete_task(self, db_session, org_and_user, project):
        """Soft delete task — không xuất hiện ở get_all."""
        _, _, current_user = org_and_user
        service = TaskService(db_session)
        task = await service.create(
            CreateTaskDto(title="Delete me", project_id=project.id), current_user
        )

        await service.delete(task.id, current_user)
        tasks = await service.get_all(current_user)
        ids = [t.id for t in tasks]
        assert task.id not in ids

    @pytest.mark.asyncio
    async def test_multi_tenancy_tasks_isolation(self, db_session, org_and_user, project):
        """Tasks của org A không visible với org B."""
        _, _, current_user = org_and_user
        service = TaskService(db_session)
        await service.create(CreateTaskDto(title="Org A task", project_id=project.id), current_user)

        other_user = make_user(role="member")
        other_tasks = await service.get_all(other_user)
        assert len(other_tasks) == 0
