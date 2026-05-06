"""
SQLAlchemy Models â€” Táº¥t cáº£ cÃ¡c báº£ng trong HYLIST.

Quy táº¯c thiáº¿t káº¿ (tá»« backend/SKILL.md):
  - Má»i table cÃ³: id (UUID), org_id (multi-tenancy), created_at, updated_at, deleted_at
  - Soft delete: KHÃ”NG xÃ³a tháº­t â€” set deleted_at (cáº§n data cho ML training)
  - ML fields: báº¯t buá»™c collect tá»« Tuáº§n 1, dÃ¹ Phase 2 má»›i train
"""

import enum
import json
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from ..core.database import Base


class JSONList(TypeDecorator):
    """
    Custom type Ä‘á»ƒ lÆ°u list[str] dÆ°á»›i dáº¡ng JSON.
    - Vá»›i PostgreSQL: táº­n dá»¥ng native JSON support.
    - Vá»›i SQLite (test): serialize thÃ nh JSON string.
    DÃ¹ng thay tháº¿ ARRAY(String) Ä‘á»ƒ cross-database compatible.
    """

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return value  # JSON handles serialization

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value


# â”€â”€â”€ Enums â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class UserRole(str, enum.Enum):  # noqa: UP042
    ADMIN = "admin"  # XÃ³a org, manage users
    MANAGER = "manager"  # Manage projects, assign tasks
    MEMBER = "member"  # CRUD tasks cá»§a báº£n thÃ¢n
    VIEWER = "viewer"  # Read-only


class TaskStatus(str, enum.Enum):  # noqa: UP042
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"


class ProjectStatus(str, enum.Enum):  # noqa: UP042
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


# â”€â”€â”€ Organization (Multi-tenancy base) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class Organization(Base):
    """
    Tá»• chá»©c / Workspace â€” Ä‘Æ¡n vá»‹ cÃ´ láº­p dá»¯ liá»‡u cao nháº¥t.
    Má»i resource Ä‘á»u thuá»™c vá» 1 org.
    """

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
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


# â”€â”€â”€ User â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default=UserRole.MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Workload tracking (dÃ¹ng cho ML feature: assignee_workload)
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


# â”€â”€â”€ Project â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
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


# â”€â”€â”€ Task (Main entity â€” tÃ¢m Ä‘iá»ƒm cá»§a toÃ n há»‡ thá»‘ng) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class Task(Base):
    """
    Task lÃ  entity trung tÃ¢m. Thiáº¿t káº¿ vá»›i Ä‘áº§y Ä‘á»§ ML-ready fields tá»« Tuáº§n 1.

    Táº¡i sao cáº§n nhiá»u fields ngay tá»« Ä‘áº§u?
    â†’ Phase 2 (Tuáº§n 5) cáº§n data history Ä‘á»ƒ train XGBoost.
    â†’ Náº¿u thiáº¿u field â†’ pháº£i backfill â†’ khÃ´ng cÃ³ historical data.
    â†’ Rule: Collect dá»¯ liá»‡u trÆ°á»›c khi cáº§n, khÃ´ng pháº£i sau.
    """

    __tablename__ = "tasks"

    # â”€â”€â”€ Identity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assignee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # â”€â”€â”€ Core fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=TaskStatus.TODO)
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False, default=3)  # 1â€“5

    # â”€â”€â”€ Time tracking (TARGET VARIABLE cho ML regression) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    estimated_time: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # hours â€” user input
    actual_time: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # hours â€” ghi khi DONE
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # â”€â”€â”€ ML Feature Fields (Phase 2 sáº½ dÃ¹ng) â€” pháº£i collect tá»« Tuáº§n 1 â”€â”€â”€â”€â”€â”€â”€
    dependency_count: Mapped[int] = mapped_column(Integer, default=0)  # Sá»‘ tasks block task nÃ y
    subtask_count: Mapped[int] = mapped_column(Integer, default=0)  # Sá»‘ subtasks
    assignee_workload: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # 0.0â€“1.0 capacity lÃºc assign
    revision_count: Mapped[int] = mapped_column(Integer, default=0)  # Sá»‘ láº§n edit/reopen
    context_switch_count: Mapped[int] = mapped_column(Integer, default=0)  # Sá»‘ láº§n pause/resume
    blocked_duration_hrs: Mapped[float] = mapped_column(Float, default=0.0)  # Giá» bá»‹ block
    deadline_buffer_hrs: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Giá» cÃ²n láº¡i khi assign
    first_status_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # â”€â”€â”€ NLP Output (Phase 3 sáº½ Ä‘iá»n) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    tags: Mapped[list[str] | None] = mapped_column(JSONList, nullable=True)  # ["Bug", "Frontend"]
    nlp_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # â”€â”€â”€ Privacy / GDPR â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    allow_ml_training: Mapped[bool] = mapped_column(Boolean, default=True)  # User cÃ³ thá»ƒ opt-out

    # â”€â”€â”€ Audit & Soft Delete â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€â”€ AuditLog (Báº¯t buá»™c â€” data cho ML training) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class AuditLog(Base):
    """
    Ghi láº¡i Má»ŒI state change cá»§a Task.

    Táº¡i sao quan trá»ng?
    â†’ KhÃ´ng cÃ³ AuditLog â†’ khÃ´ng biáº¿t task Ä‘Æ°á»£c sá»­a bao nhiÃªu láº§n
    â†’ revision_count, blocked_duration_hrs â†’ cáº§n tÃ­nh tá»« AuditLog
    â†’ KHÃ”NG gá»i thá»§ cÃ´ng trong service â€” middleware tá»± Ä‘á»™ng ghi
    """

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    task_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "task", "project"
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "created", "updated", "deleted", "status_changed"
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Tráº¡ng thÃ¡i trÆ°á»›c
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Tráº¡ng thÃ¡i sau
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    task: Mapped["Task | None"] = relationship("Task", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_org_id", "org_id"),
        Index("ix_audit_logs_entity_id", "entity_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
        # Auto-cleanup: XÃ³a logs > 90 ngÃ y (cáº¥u hÃ¬nh PostgreSQL pg_partman hoáº·c cron)
    )


# â”€â”€â”€ Export â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
