"""Projects Router — /api/v1/projects"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.security import get_current_user, CurrentUser
from ...core.auth import require_role, Role
from ...schemas.project import CreateProjectDto, UpdateProjectDto, ProjectOut
from ...schemas.common import SuccessResponse
from ...services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/", response_model=SuccessResponse[ProjectOut], status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_project(
    request: Request,
    dto: CreateProjectDto,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.MEMBER)),
):
    """Tạo Project mới. Yêu cầu quyền MEMBER trở lên."""
    try:
        service = ProjectService(db)
        project = await service.create(dto, current_user)
        await db.commit()
        return SuccessResponse(data=project, message="Tạo project thành công")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=SuccessResponse[list[ProjectOut]])
@limiter.limit("60/minute")
async def list_projects(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    """Lấy danh sách tất cả Projects trong Org."""
    service = ProjectService(db)
    projects = await service.get_all(current_user)
    return SuccessResponse(data=projects)


@router.get("/{project_id}", response_model=SuccessResponse[ProjectOut])
@limiter.limit("60/minute")
async def get_project(
    request: Request,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    """Lấy chi tiết một Project theo ID."""
    try:
        service = ProjectService(db)
        project = await service.get_by_id(project_id, current_user)
        return SuccessResponse(data=project)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{project_id}", response_model=SuccessResponse[ProjectOut])
@limiter.limit("30/minute")
async def update_project(
    request: Request,
    project_id: UUID,
    dto: UpdateProjectDto,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.MEMBER)),
):
    """Cập nhật Project. Yêu cầu quyền MEMBER trở lên."""
    try:
        service = ProjectService(db)
        project = await service.update(project_id, dto, current_user)
        await db.commit()
        return SuccessResponse(data=project, message="Cập nhật thành công")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{project_id}", response_model=SuccessResponse[dict])
@limiter.limit("10/minute")
async def delete_project(
    request: Request,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN)),
):
    """Xóa Project (soft delete). Chỉ ADMIN mới được phép."""
    try:
        service = ProjectService(db)
        result = await service.delete(project_id, current_user)
        await db.commit()
        return SuccessResponse(data=result, message="Xóa project thành công")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
