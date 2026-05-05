"""Task schemas — theo openapi.yaml contract."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Input ─────────────────────────────────────────────────────────────────────

class CreateTaskDto(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    project_id: UUID
    description: str | None = Field(None, max_length=5000)
    priority_score: int = Field(3, ge=1, le=5)
    estimated_time: float | None = Field(None, gt=0, description="Estimated hours")
    deadline: datetime | None = None
    assignee_id: UUID | None = None


class UpdateTaskDto(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    status: str | None = Field(None, pattern=r"^(todo|in_progress|review|done|cancelled)$")
    priority_score: int | None = Field(None, ge=1, le=5)
    estimated_time: float | None = Field(None, gt=0)
    actual_time: float | None = Field(None, gt=0)
    deadline: datetime | None = None
    assignee_id: UUID | None = None


# ── Output ────────────────────────────────────────────────────────────────────

class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    project_id: UUID
    description: str | None
    status: str
    priority_score: int
    estimated_time: float | None
    actual_time: float | None
    tags: list[str] | None
    assignee_id: UUID | None
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime | None
