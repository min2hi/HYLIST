"""Task Service — CRUD logic, multi-tenancy + ML field collection."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import CurrentUser
from ..models import Task, TaskStatus, User
from ..schemas.task import CreateTaskDto, TaskOut, UpdateTaskDto

logger = structlog.get_logger()


class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── CREATE ────────────────────────────────────────────────────────────────
    async def create(self, dto: CreateTaskDto, user: CurrentUser) -> TaskOut:
        # Tính assignee_workload nếu có assignee (ML feature)
        assignee_workload = None
        if dto.assignee_id:
            stmt = select(User.current_task_count, User.max_task_capacity).where(
                User.id == dto.assignee_id, User.org_id == user.org_id
            )
            result = await self.db.execute(stmt)
            row = result.one_or_none()
            if row and row.max_task_capacity > 0:
                assignee_workload = row.current_task_count / row.max_task_capacity

        # FIX SEC-2: Dùng datetime.now(UTC) thay vì datetime.utcnow() (deprecated Python 3.12)
        now = datetime.now(UTC)

        # Tính deadline_buffer_hrs (ML feature)
        deadline_buffer_hrs = None
        if dto.deadline:
            delta = dto.deadline - now
            deadline_buffer_hrs = delta.total_seconds() / 3600

        task = Task(
            org_id=user.org_id,
            project_id=dto.project_id,
            created_by=user.id,
            assignee_id=dto.assignee_id,
            title=dto.title.strip(),
            description=dto.description,
            priority_score=dto.priority_score,
            estimated_time=dto.estimated_time,
            deadline=dto.deadline,
            status=TaskStatus.TODO,
            # ML fields — collect ngay từ lúc tạo
            assignee_workload=assignee_workload,
            deadline_buffer_hrs=deadline_buffer_hrs,
        )
        self.db.add(task)
        await self.db.flush()

        # Tăng task count của assignee
        if dto.assignee_id:
            await self.db.execute(
                update(User)
                .where(User.id == dto.assignee_id)
                .values(current_task_count=User.current_task_count + 1)
            )

        logger.info("task_created", id=str(task.id), org_id=str(user.org_id))
        return TaskOut.model_validate(task)

    # ── GET ALL ───────────────────────────────────────────────────────────────
    async def get_all(self, user: CurrentUser, project_id: UUID | None = None) -> list[TaskOut]:
        stmt = select(Task).where(
            Task.org_id == user.org_id,
            Task.deleted_at.is_(None),
        )
        if project_id:
            stmt = stmt.where(Task.project_id == project_id)

        stmt = stmt.order_by(Task.created_at.desc())
        result = await self.db.execute(stmt)
        return [TaskOut.model_validate(t) for t in result.scalars().all()]

    # ── GET BY ID ─────────────────────────────────────────────────────────────
    async def get_by_id(self, task_id: UUID, user: CurrentUser) -> TaskOut:
        stmt = select(Task).where(
            Task.id == task_id,
            Task.org_id == user.org_id,  # Chặn IDOR
            Task.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            raise ValueError("Task không tồn tại hoặc bạn không có quyền truy cập")
        return TaskOut.model_validate(task)

    # ── UPDATE ────────────────────────────────────────────────────────────────
    async def update(self, task_id: UUID, dto: UpdateTaskDto, user: CurrentUser) -> TaskOut:
        existing = await self.get_by_id(task_id, user)

        # FIX SEC-2: datetime.now(UTC) thay cho datetime.utcnow()
        now = datetime.now(UTC)

        update_data: dict = {}
        if dto.title is not None:
            update_data["title"] = dto.title.strip()
            update_data["revision_count"] = Task.revision_count + 1  # ML field
        if dto.description is not None:
            update_data["description"] = dto.description
        if dto.status is not None:
            update_data["status"] = dto.status
            # Ghi nhận thời điểm status đổi lần đầu (ML field)
            if not existing.updated_at:
                update_data["first_status_change_at"] = now
            # Nếu xong task — ghi actual completion time
            if dto.status == TaskStatus.DONE:
                update_data["completed_at"] = now
        if dto.priority_score is not None:
            update_data["priority_score"] = dto.priority_score
        if dto.estimated_time is not None:
            update_data["estimated_time"] = dto.estimated_time
        if dto.actual_time is not None:
            update_data["actual_time"] = dto.actual_time
        if dto.deadline is not None:
            update_data["deadline"] = dto.deadline
        if dto.assignee_id is not None:
            update_data["assignee_id"] = dto.assignee_id

        if not update_data:
            return existing

        update_data["updated_at"] = now
        await self.db.execute(update(Task).where(Task.id == task_id).values(**update_data))
        await self.db.flush()

        logger.info("task_updated", id=str(task_id), fields=list(update_data.keys()))
        return await self.get_by_id(task_id, user)

    # ── SOFT DELETE ───────────────────────────────────────────────────────────
    async def delete(self, task_id: UUID, user: CurrentUser) -> dict:
        await self.get_by_id(task_id, user)

        # FIX SEC-2: datetime.now(UTC)
        await self.db.execute(
            update(Task).where(Task.id == task_id).values(deleted_at=datetime.now(UTC))
        )
        await self.db.flush()

        logger.info("task_deleted", id=str(task_id))
        return {"deleted": True, "id": str(task_id)}
