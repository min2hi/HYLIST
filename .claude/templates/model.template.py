# model.template.py — SQLAlchemy ORM Model Template
# ============================================================
# HƯỚNG DẪN:
#   1. Copy → đổi tên thành `<tên>.py` trong models/
#   2. Tìm-Thay "Example"/"examples" → tên feature
#   3. Thêm/xóa columns theo nhu cầu
#   4. Tạo Alembic migration sau khi sửa
#   5. Xóa comment hướng dẫn (#*)
# ============================================================

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..core.database import Base


class Example(Base):  #* Đổi tên class
    __tablename__ = "examples"  #* Đổi tên bảng

    # =========================================================
    # PRIMARY KEY — dùng UUID, không phải integer
    # =========================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # =========================================================
    # MULTI-TENANCY — BẮT BUỘC có trong mọi table
    # =========================================================
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)

    # =========================================================
    # OWNERSHIP
    # =========================================================
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # =========================================================
    # BUSINESS FIELDS #* Thêm fields nghiệp vụ vào đây
    # =========================================================
    name        = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # =========================================================
    # AUDIT TIMESTAMPS — BẮT BUỘC có trong mọi table
    # =========================================================
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  #* Soft delete — không xóa thật

    # =========================================================
    # RELATIONSHIPS #* Thêm relationships nếu cần
    # =========================================================
    # organization = relationship("Organization", back_populates="examples")
    # creator = relationship("User", foreign_keys=[created_by])
