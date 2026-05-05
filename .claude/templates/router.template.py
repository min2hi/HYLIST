# router.template.py — HYLIST Backend Router Template
# ============================================================
# HƯỚNG DẪN:
#   1. Copy → đổi tên thành `<tên>.py` trong api/v1/
#   2. Tìm-Thay "example"/"Example" → tên feature
#   3. Đăng ký trong main.py: app.include_router(example_router, prefix="/api/v1")
#   4. Xóa comment hướng dẫn (#*)
# ============================================================
# NGUYÊN TẮC:
#   ✅ Router chỉ xử lý HTTP: nhận request, gọi service, trả response
#   ✅ Business logic KHÔNG nằm ở đây — nằm trong Service
#   ✅ Idempotency check cho POST/PUT
#   ✅ Rate limiting trên mọi endpoint
#   ❌ KHÔNG gọi SQLAlchemy trực tiếp ở đây
# ============================================================

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.auth import CurrentUser, require_role, Role
from ...core.rate_limit import limiter
from ...core.redis import redis_client
from ...schemas.example import CreateExampleDto, UpdateExampleDto, ExampleOut  #* Đổi import
from ...schemas.common import SuccessResponse
from ...services.example.service import ExampleService  #* Đổi import

router = APIRouter(prefix="/examples", tags=["examples"])  #* Đổi prefix


# =========================================================
# POST /examples/
# =========================================================
@router.post("/", response_model=SuccessResponse[ExampleOut], status_code=201)
@limiter.limit("30/minute")
async def create_example(  #* Đổi tên function
    request: Request,
    dto: CreateExampleDto,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.MEMBER)),
):
    #* Idempotency check — ngăn tạo duplicate khi retry
    cached = await redis_client.get(f"idem:{idempotency_key}")
    if cached:
        return json.loads(cached)

    service = ExampleService(db)
    result = await service.create(dto, current_user)

    response = SuccessResponse(data=result)
    await redis_client.setex(f"idem:{idempotency_key}", 86400, response.model_dump_json())
    return response


# =========================================================
# GET /examples/
# =========================================================
@router.get("/", response_model=SuccessResponse[list[ExampleOut]])
@limiter.limit("60/minute")
async def get_all_examples(  #* Đổi tên function
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    service = ExampleService(db)
    results = await service.get_all(current_user)
    return SuccessResponse(data=results)


# =========================================================
# GET /examples/{id}
# =========================================================
@router.get("/{id}", response_model=SuccessResponse[ExampleOut])
@limiter.limit("60/minute")
async def get_example_by_id(  #* Đổi tên function
    request: Request,
    id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.VIEWER)),
):
    service = ExampleService(db)
    result = await service.get_by_id(id, current_user)
    return SuccessResponse(data=result)


# =========================================================
# PATCH /examples/{id}
# =========================================================
@router.patch("/{id}", response_model=SuccessResponse[ExampleOut])
@limiter.limit("30/minute")
async def update_example(  #* Đổi tên function
    request: Request,
    id: UUID,
    dto: UpdateExampleDto,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.MEMBER)),
):
    service = ExampleService(db)
    result = await service.update(id, dto, current_user)
    return SuccessResponse(data=result)


# =========================================================
# DELETE /examples/{id}
# =========================================================
@router.delete("/{id}", response_model=SuccessResponse[dict])
@limiter.limit("10/minute")
async def delete_example(  #* Đổi tên function
    request: Request,
    id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN)),  #* Chỉ ADMIN mới xóa
):
    service = ExampleService(db)
    result = await service.delete(id, current_user)
    return SuccessResponse(data=result)
