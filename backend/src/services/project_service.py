"""Project Service — CRUD logic, multi-tenancy enforced."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import CurrentUser
from ..models import Project, ProjectStatus
from ..schemas.project import CreateProjectDto, ProjectOut, UpdateProjectDto

logger = structlog.get_logger()


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── CREATE ────────────────────────────────────────────────────────────────
    async def create(self, dto: CreateProjectDto, user: CurrentUser) -> ProjectOut:
        project = Project(
            org_id=user.org_id,  # Multi-tenancy: luôn lấy từ user
            created_by=user.id,
            name=dto.name.strip(),
            description=dto.description,
            color=dto.color,
            status=ProjectStatus.ACTIVE,
        )
        self.db.add(project)
        await self.db.flush()

        logger.info("project_created", id=str(project.id), org_id=str(user.org_id))
        return ProjectOut.model_validate(project)

    # ── GET ALL (của org) ─────────────────────────────────────────────────────
    async def get_all(self, user: CurrentUser) -> list[ProjectOut]:
        stmt = (
            select(Project)
            .where(Project.org_id == user.org_id, Project.deleted_at.is_(None))
            .order_by(Project.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return [ProjectOut.model_validate(p) for p in result.scalars().all()]

    # ── GET BY ID ─────────────────────────────────────────────────────────────
    async def get_by_id(self, project_id: UUID, user: CurrentUser) -> ProjectOut:
        stmt = select(Project).where(
            Project.id == project_id,
            Project.org_id == user.org_id,  # Chặn IDOR
            Project.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        project = result.scalar_one_or_none()

        if not project:
            raise ValueError("Project không tồn tại hoặc bạn không có quyền truy cập")
        return ProjectOut.model_validate(project)

    # ── UPDATE ────────────────────────────────────────────────────────────────
    async def update(
        self, project_id: UUID, dto: UpdateProjectDto, user: CurrentUser
    ) -> ProjectOut:
        # Verify ownership trước
        await self.get_by_id(project_id, user)

        update_data: dict = {}
        if dto.name is not None:
            update_data["name"] = dto.name.strip()
        if dto.description is not None:
            update_data["description"] = dto.description
        if dto.color is not None:
            update_data["color"] = dto.color
        if dto.status is not None:
            update_data["status"] = dto.status

        if not update_data:
            return await self.get_by_id(project_id, user)

        # FIX SEC-2: datetime.now(UTC) thay cho datetime.utcnow() (deprecated Python 3.12)
        update_data["updated_at"] = datetime.now(UTC)
        await self.db.execute(update(Project).where(Project.id == project_id).values(**update_data))
        await self.db.flush()

        logger.info("project_updated", id=str(project_id), fields=list(update_data.keys()))
        return await self.get_by_id(project_id, user)

    # ── SOFT DELETE ───────────────────────────────────────────────────────────
    async def delete(self, project_id: UUID, user: CurrentUser) -> dict:
        await self.get_by_id(project_id, user)

        # FIX SEC-2: datetime.now(UTC)
        await self.db.execute(
            update(Project).where(Project.id == project_id).values(deleted_at=datetime.now(UTC))
        )
        await self.db.flush()

        logger.info("project_deleted", id=str(project_id))
        return {"deleted": True, "id": str(project_id)}
