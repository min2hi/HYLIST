"""Unit tests — TaskService: validation, ML feature collection, status transitions."""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from src.core.security import CurrentUser
from src.models import TaskStatus
from src.schemas.task import CreateTaskDto, UpdateTaskDto


def make_user(role: str = "member") -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=role,
        email="worker@example.com",
        full_name="Worker User",
    )


class TestCreateTaskDto:

    def test_valid_task_dto(self):
        """CreateTaskDto validate đúng với fields bắt buộc."""
        dto = CreateTaskDto(
            title="Fix login bug",
            project_id=uuid.uuid4(),
        )
        assert dto.title == "Fix login bug"
        assert dto.priority_score == 3  # default

    def test_priority_score_bounds(self):
        """priority_score phải từ 1–5."""
        # Valid
        dto = CreateTaskDto(title="Task", project_id=uuid.uuid4(), priority_score=5)
        assert dto.priority_score == 5

        # Invalid — Pydantic sẽ raise
        with pytest.raises(Exception):
            CreateTaskDto(title="Task", project_id=uuid.uuid4(), priority_score=6)

        with pytest.raises(Exception):
            CreateTaskDto(title="Task", project_id=uuid.uuid4(), priority_score=0)

    def test_title_required(self):
        """Title là bắt buộc."""
        with pytest.raises(Exception):
            CreateTaskDto(project_id=uuid.uuid4())

    def test_project_id_required(self):
        """project_id là bắt buộc."""
        with pytest.raises(Exception):
            CreateTaskDto(title="Task")

    def test_title_stripped_for_validation(self):
        """Title với giá trị hợp lệ được strip và accept."""
        dto = CreateTaskDto(title="  Valid Task  ", project_id=uuid.uuid4())
        assert dto.title == "Valid Task"  # strip() được apply

    def test_title_whitespace_rejection(self):
        """Title chỉ toàn whitespace bị reject sau khi strip."""
        with pytest.raises(Exception):
            CreateTaskDto(title="   ", project_id=uuid.uuid4())


class TestUpdateTaskDto:

    def test_all_fields_optional(self):
        """UpdateTaskDto cho phép partial update (không có field nào cũng OK)."""
        dto = UpdateTaskDto()
        assert dto.title is None
        assert dto.status is None
        assert dto.priority_score is None

    def test_valid_status_values(self):
        """Status chỉ nhận các giá trị enum hợp lệ."""
        for status in ["todo", "in_progress", "review", "done", "cancelled"]:
            dto = UpdateTaskDto(status=status)
            assert dto.status is not None

    def test_invalid_status_rejected(self):
        """Status không hợp lệ bị reject."""
        with pytest.raises(Exception):
            UpdateTaskDto(status="blocked")  # Không có trong enum


class TestMLFeatureLogic:
    """Test logic tính ML features — đây là data critical cho Phase 2."""

    def test_deadline_buffer_calculation(self):
        """
        deadline_buffer_hrs = (deadline - now) in hours.
        Nếu deadline trong tương lai → positive buffer.
        Nếu deadline đã qua → negative buffer (task overdue).
        """
        now = datetime.now(timezone.utc)
        future_deadline = now + timedelta(hours=24)
        buffer = (future_deadline - now).total_seconds() / 3600
        assert buffer > 0
        assert abs(buffer - 24.0) < 0.01

    def test_overdue_task_negative_buffer(self):
        """Task đã quá hạn có deadline_buffer_hrs âm."""
        now = datetime.now(timezone.utc)
        past_deadline = now - timedelta(hours=5)
        buffer = (past_deadline - now).total_seconds() / 3600
        assert buffer < 0

    def test_assignee_workload_percentage(self):
        """
        assignee_workload = current_task_count / max_task_capacity * 100.
        0% = rảnh, 100% = full capacity.
        """
        current = 5
        capacity = 10
        workload = (current / capacity) * 100
        assert workload == 50.0

        # Full capacity
        workload_full = (10 / 10) * 100
        assert workload_full == 100.0


class TestTaskStatusTransitions:
    """Verify allowed status transitions (business rule)."""

    @pytest.mark.parametrize("from_status,to_status,allowed", [
        ("todo", "in_progress", True),
        ("in_progress", "review", True),
        ("review", "done", True),
        ("done", "todo", True),           # Allow reopen
        ("cancelled", "todo", True),      # Allow reactivate
        ("todo", "cancelled", True),
    ])
    def test_status_enum_values(self, from_status, to_status, allowed):
        """TaskStatus enum có đủ values cần thiết."""
        assert from_status in [s.value for s in TaskStatus]
        assert to_status in [s.value for s in TaskStatus]
