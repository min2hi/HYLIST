"""Task schemas — theo openapi.yaml contract."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Input ─────────────────────────────────────────────────────────────────────


class CreateTaskDto(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    project_id: UUID
    description: str | None = Field(None, max_length=5000)
    priority_score: int = Field(3, ge=1, le=5)
    estimated_time: float | None = Field(None, gt=0, description="Estimated hours")
    deadline: datetime | None = None
    assignee_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_whitespace(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title không được chỉ chứa khoảng trắng")
        return stripped


class UpdateTaskDto(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    status: str | None = Field(None, pattern=r"^(todo|in_progress|review|done|cancelled)$")
    priority_score: int | None = Field(None, ge=1, le=5)
    estimated_time: float | None = Field(None, gt=0)
    actual_time: float | None = Field(None, gt=0)
    deadline: datetime | None = None
    assignee_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_whitespace(cls, v: str | None) -> str | None:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Title không được chỉ chứa khoảng trắng")
            return stripped
        return v


# ── Output ────────────────────────────────────────────────────────────────────


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    title: str
    project_id: UUID
    created_by: UUID
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
