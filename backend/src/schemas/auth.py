"""Auth schemas — Login, Register, Token."""
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Input ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Tối thiểu 8 ký tự")
    full_name: str = Field(..., min_length=2, max_length=255)
    org_name: str = Field(..., min_length=2, max_length=255, description="Tên tổ chức / workspace")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


# ── Output ────────────────────────────────────────────────────────────────────

class TokenData(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    org_id: str
