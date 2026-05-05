"""
SQLAlchemy Models — Tất cả các bảng trong HYLIST.

Quy tắc thiết kế (từ backend/SKILL.md):
  - Mọi table có: id (UUID), org_id (multi-tenancy), created_at, updated_at, deleted_at
  - Soft delete: KHÔNG xóa thật — set deleted_at (cần data cho ML training)
  - ML fields: bắt buộc collect từ Tuần 1, dù Phase 2 mới train
"""

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base

# ─── Enums ─────────────────────────────────────────────────────────────────────


class UserRole(str, enum.Enum):
    ADMIN = "admin"  # Xóa org, manage users
    MANAGER = "manager"  # Manage projects, assign tasks
    MEMBER = "member"  # CRUD tasks của bản thân
    VIEWER = "viewer"  # Read-only


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


# ─── Organization (Multi-tenancy base) ─────────────────────────────────────────


class Organization(Base):
    """
    Tổ chức / Workspace — đơn vị cô lập dữ liệu cao nhất.
    Mọi resource đều thuộc về 1 org.
    """

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="organization")


# ─── User ──────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default=UserRole.MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Workload tracking (dùng cho ML feature: assignee_workload)
    current_task_count: Mapped[int] = mapped_column(Integer, default=0)
    max_task_capacity: Mapped[int] = mapped_column(Integer, default=10)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="users")
    created_tasks: Mapped[list["Task"]] = relationship(
        "Task", foreign_keys="Task.created_by", back_populates="creator"
    )
    assigned_tasks: Mapped[list["Task"]] = relationship(
        "Task", foreign_keys="Task.assignee_id", back_populates="assignee"
    )

    __table_args__ = (
        Index("ix_users_org_id", "org_id"),
        Index("ix_users_email", "email"),
    )


# ─── Project ───────────────────────────────────────────────────────────────────


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=ProjectStatus.ACTIVE)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # Hex color

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="project")

    __table_args__ = (Index("ix_projects_org_id", "org_id"),)


# ─── Task (Main entity — tâm điểm của toàn hệ thống) ─────────────────────────


class Task(Base):
    """
    Task là entity trung tâm. Thiết kế với đầy đủ ML-ready fields từ Tuần 1.

    Tại sao cần nhiều fields ngay từ đầu?
    → Phase 2 (Tuần 5) cần data history để train XGBoost.
    → Nếu thiếu field → phải backfill → không có historical data.
    → Rule: Collect dữ liệu trước khi cần, không phải sau.
    """

    __tablename__ = "tasks"

    # ─── Identity ────────────────────────────────────────────────────────────
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assignee_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # ─── Core fields ─────────────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=TaskStatus.TODO)
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False, default=3)  # 1–5

    # ─── Time tracking (TARGET VARIABLE cho ML regression) ───────────────────
    estimated_time: Mapped[float | None] = mapped_column(Float, nullable=True)  # hours — user input
    actual_time: Mapped[float | None] = mapped_column(Float, nullable=True)  # hours — ghi khi DONE
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ─── ML Feature Fields (Phase 2 sẽ dùng) — phải collect từ Tuần 1 ───────
    dependency_count: Mapped[int] = mapped_column(Integer, default=0)  # Số tasks block task này
    subtask_count: Mapped[int] = mapped_column(Integer, default=0)  # Số subtasks
    assignee_workload: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # 0.0–1.0 capacity lúc assign
    revision_count: Mapped[int] = mapped_column(Integer, default=0)  # Số lần edit/reopen
    context_switch_count: Mapped[int] = mapped_column(Integer, default=0)  # Số lần pause/resume
    blocked_duration_hrs: Mapped[float] = mapped_column(Float, default=0.0)  # Giờ bị block
    deadline_buffer_hrs: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Giờ còn lại khi assign
    first_status_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ─── NLP Output (Phase 3 sẽ điền) ───────────────────────────────────────
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )  # ["Bug", "Frontend"]
    nlp_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ─── Privacy / GDPR ──────────────────────────────────────────────────────
    allow_ml_training: Mapped[bool] = mapped_column(Boolean, default=True)  # User có thể opt-out

    # ─── Audit & Soft Delete ─────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Soft delete

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="tasks")
    creator: Mapped["User"] = relationship(
        "User", foreign_keys=[created_by], back_populates="created_tasks"
    )
    assignee: Mapped["User | None"] = relationship(
        "User", foreign_keys=[assignee_id], back_populates="assigned_tasks"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="task")

    __table_args__ = (
        Index("ix_tasks_org_id", "org_id"),
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_assignee_id", "assignee_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_created_at", "created_at"),
    )


# ─── AuditLog (Bắt buộc — data cho ML training) ───────────────────────────────


class AuditLog(Base):
    """
    Ghi lại MỌI state change của Task.

    Tại sao quan trọng?
    → Không có AuditLog → không biết task được sửa bao nhiêu lần
    → revision_count, blocked_duration_hrs → cần tính từ AuditLog
    → KHÔNG gọi thủ công trong service — middleware tự động ghi
    """

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "task", "project"
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "created", "updated", "deleted", "status_changed"
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Trạng thái trước
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Trạng thái sau
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    task: Mapped["Task | None"] = relationship("Task", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_org_id", "org_id"),
        Index("ix_audit_logs_entity_id", "entity_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
        # Auto-cleanup: Xóa logs > 90 ngày (cấu hình PostgreSQL pg_partman hoặc cron)
    )


# ─── Export ────────────────────────────────────────────────────────────────────
__all__ = [
    "Base",
    "Organization",
    "User",
    "Project",
    "Task",
    "AuditLog",
    "UserRole",
    "TaskStatus",
    "ProjectStatus",
]
