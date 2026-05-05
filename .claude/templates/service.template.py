# service.template.py — HYLIST Backend Service Template
# ============================================================
# HƯỚNG DẪN:
#   1. Copy → đổi tên thành `<tên>.service.py`
#   2. Tìm-Thay "Example"/"example" → tên feature của bạn
#   3. Xóa các comment hướng dẫn (#*)
#   4. Xóa method không cần thiết
# ============================================================
# NGUYÊN TẮC:
#   ✅ Toàn bộ business logic nằm ở đây, KHÔNG nằm trong Router
#   ✅ Nhận AsyncSession qua __init__ (dependency injection)
#   ✅ Validate input ở đầu mỗi method trước khi query DB
#   ✅ Filter theo org_id (multi-tenancy) + user.id (IDOR) mọi query
#   ✅ Dùng select() chỉ lấy fields cần thiết
#   ❌ KHÔNG import Request/Response
#   ❌ KHÔNG dùng pickle
# ============================================================

from uuid import UUID
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from ..models.example import Example  #* Đổi import
from ..schemas.example import CreateExampleDto, UpdateExampleDto, ExampleOut  #* Đổi import
from ..core.auth import CurrentUser

logger = structlog.get_logger()


class ExampleService:  #* Đổi tên class

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================
    # CREATE
    # =========================================================
    async def create(self, dto: CreateExampleDto, user: CurrentUser) -> ExampleOut:
        #* Bước 1: Validate input
        if not dto.name or not dto.name.strip():
            raise ValueError("Name không được để trống")

        #* Bước 2: Kiểm tra duplicate nếu cần
        # existing = await self._find_by_name(dto.name, user.org_id)
        # if existing:
        #     raise ValueError("Tên này đã tồn tại trong tổ chức")

        #* Bước 3: Tạo record — LUÔN set org_id từ user (multi-tenancy)
        record = Example(
            org_id=user.org_id,       #* Bắt buộc — multi-tenancy
            created_by=user.id,
            name=dto.name.strip(),
        )
        self.db.add(record)
        await self.db.flush()

        logger.info("example_created", id=str(record.id), org_id=str(user.org_id))
        return ExampleOut.model_validate(record)

    # =========================================================
    # GET ALL (của org)
    # =========================================================
    async def get_all(self, user: CurrentUser) -> list[ExampleOut]:
        #* LUÔN filter theo org_id
        stmt = (
            select(Example.id, Example.name, Example.created_at)
            .where(Example.org_id == user.org_id, Example.deleted_at.is_(None))
            .order_by(Example.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return [ExampleOut.model_validate(row._asdict()) for row in result.all()]

    # =========================================================
    # GET BY ID (với ownership check)
    # =========================================================
    async def get_by_id(self, record_id: UUID, user: CurrentUser) -> ExampleOut:
        #* Filter theo org_id + id — ngăn IDOR
        stmt = select(Example).where(
            Example.id == record_id,
            Example.org_id == user.org_id,
            Example.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            raise ValueError("Không tìm thấy hoặc bạn không có quyền truy cập")
        return ExampleOut.model_validate(record)

    # =========================================================
    # UPDATE
    # =========================================================
    async def update(self, record_id: UUID, dto: UpdateExampleDto, user: CurrentUser) -> ExampleOut:
        #* Verify ownership trước khi update
        record = await self.get_by_id(record_id, user)

        update_data: dict = {}
        if dto.name is not None:
            update_data["name"] = dto.name.strip()

        if not update_data:
            return record

        await self.db.execute(
            update(Example)
            .where(Example.id == record_id)
            .values(**update_data, updated_at=datetime.utcnow())
        )
        await self.db.flush()

        logger.info("example_updated", id=str(record_id), fields=list(update_data.keys()))
        return await self.get_by_id(record_id, user)

    # =========================================================
    # SOFT DELETE
    # =========================================================
    async def delete(self, record_id: UUID, user: CurrentUser) -> dict:
        #* Verify ownership trước khi xóa
        await self.get_by_id(record_id, user)

        #* Soft delete — KHÔNG xóa thật (GDPR + data integrity)
        await self.db.execute(
            update(Example)
            .where(Example.id == record_id)
            .values(deleted_at=datetime.utcnow())
        )
        await self.db.flush()

        logger.info("example_soft_deleted", id=str(record_id))
        return {"deleted": True, "id": str(record_id)}

    #* =========================================================
    #* Thêm các method nghiệp vụ đặc thù bên dưới đây
    #* =========================================================
