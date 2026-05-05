"""Project schemas — theo openapi.yaml contract."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Input ─────────────────────────────────────────────────────────────────────


class CreateProjectDto(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    color: str | None = Field(
        None, pattern=r"^#[0-9A-Fa-f]{6}$", description="Hex color, e.g. #FF5733"
    )


class UpdateProjectDto(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    status: str | None = Field(None, pattern=r"^(active|paused|completed|archived)$")


# ── Output ────────────────────────────────────────────────────────────────────


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    status: str
    color: str | None
    created_at: datetime
    updated_at: datetime | None
