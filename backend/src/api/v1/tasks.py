"""Tasks Router — /api/v1/tasks"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.auth import Role, require_role
from ...core.database import get_db
from ...core.security import CurrentUser
from ...schemas.common import SuccessResponse
from ...schemas.task import CreateTaskDto, TaskOut, UpdateTaskDto
from ...services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/", response_model=SuccessResponse[TaskOut], status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_task(
    request: Request,
    dto: CreateTaskDto,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.MEMBER)),
):
    """Tạo Task mới trong một Project."""
    try:
        service = TaskService(db)
        task = await service.create(dto, current_user)
        return SuccessResponse(data=task, message="Tạo task thành công")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=SuccessResponse[list[TaskOut]])
@limiter.limit("60/minute")
async def list_tasks(
    request: Request,
    project_id: UUID | None = Query(None, description="Lọc theo Project ID"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    """Lấy danh sách Tasks. Có thể lọc theo project_id."""
    service = TaskService(db)
    tasks = await service.get_all(current_user, project_id=project_id)
    return SuccessResponse(data=tasks)


@router.get("/{task_id}", response_model=SuccessResponse[TaskOut])
@limiter.limit("60/minute")
async def get_task(
    request: Request,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    """Lấy chi tiết một Task theo ID."""
    try:
        service = TaskService(db)
        task = await service.get_by_id(task_id, current_user)
        return SuccessResponse(data=task)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{task_id}", response_model=SuccessResponse[TaskOut])
@limiter.limit("30/minute")
async def update_task(
    request: Request,
    task_id: UUID,
    dto: UpdateTaskDto,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.MEMBER)),
):
    """Cập nhật Task (title, status, assignee...). Yêu cầu quyền MEMBER trở lên."""
    try:
        service = TaskService(db)
        task = await service.update(task_id, dto, current_user)
        return SuccessResponse(data=task, message="Cập nhật task thành công")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{task_id}", response_model=SuccessResponse[dict])
@limiter.limit("10/minute")
async def delete_task(
    request: Request,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.MANAGER)),
):
    """Xóa Task (soft delete). Yêu cầu quyền MANAGER trở lên."""
    try:
        service = TaskService(db)
        result = await service.delete(task_id, current_user)
        return SuccessResponse(data=result, message="Xóa task thành công")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
