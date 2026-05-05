# schema.template.py — Pydantic v2 Schema Template
# ============================================================
# HƯỚNG DẪN:
#   1. Copy → đổi tên thành `<tên>.py` trong schemas/
#   2. Tìm-Thay "Example" → tên feature
#   3. Điều chỉnh fields theo nhu cầu
#   4. Xóa comment hướng dẫn (#*)
# ============================================================
# NGUYÊN TẮC:
#   ✅ Tất cả input validation nằm ở đây (Field validators)
#   ✅ Out schema chỉ expose fields an toàn (không expose sensitive)
#   ✅ model_config = ConfigDict(from_attributes=True) để từ ORM
#   ❌ KHÔNG dùng Optional[X] — dùng X | None (Python 3.10+)
# ============================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =========================================================
# INPUT SCHEMAS (Request body)
# =========================================================

class CreateExampleDto(BaseModel):  #* Đổi tên
    name: str = Field(..., min_length=1, max_length=500, description="Tên example")
    description: str | None = Field(None, max_length=5000)
    #* Thêm fields input khác vào đây


class UpdateExampleDto(BaseModel):  #* Đổi tên
    #* Mọi field trong Update đều Optional
    name: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    #* Thêm fields update khác vào đây


# =========================================================
# OUTPUT SCHEMAS (Response body)
# =========================================================

class ExampleOut(BaseModel):  #* Đổi tên
    #* Chỉ expose fields an toàn — KHÔNG expose sensitive fields
    model_config = ConfigDict(from_attributes=True)  #* Cho phép từ ORM object

    id:          UUID
    name:        str
    description: str | None
    created_at:  datetime
    updated_at:  datetime | None
    #* KHÔNG expose: org_id nội bộ, created_by nội bộ, deleted_at


class ExampleListOut(BaseModel):  #* Đổi tên
    model_config = ConfigDict(from_attributes=True)
    id:         UUID
    name:       str
    created_at: datetime
    #* List view thường ít fields hơn detail view


# =========================================================
# COMMON RESPONSE WRAPPER — dùng lại từ schemas/common.py
# =========================================================
# from .common import SuccessResponse
# Dùng: SuccessResponse[ExampleOut], SuccessResponse[list[ExampleListOut]]
