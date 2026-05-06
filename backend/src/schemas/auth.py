"""Auth schemas — Login, Register, Token."""

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ── Input ─────────────────────────────────────────────────────────────────────

# Regex kiểm tra password strength:
# - Ít nhất 1 chữ hoa
# - Ít nhất 1 chữ thường
# - Ít nhất 1 chữ số
# - Ít nhất 8 ký tự (enforce bằng min_length)
_PASSWORD_UPPER = re.compile(r"[A-Z]")
_PASSWORD_DIGIT = re.compile(r"[0-9]")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128, description="Tối thiểu 8 ký tự")
    full_name: str = Field(..., min_length=2, max_length=255)
    org_name: str = Field(..., min_length=2, max_length=255, description="Tên tổ chức / workspace")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """
        FIX ARCH-5: Server-side password strength check.
        Big Tech standard: ít nhất 1 uppercase, 1 digit.
        Không require ký tự đặc biệt để tránh friction với người dùng.
        """
        if not _PASSWORD_UPPER.search(v):
            raise ValueError("Mật khẩu phải có ít nhất 1 chữ hoa (A-Z)")
        if not _PASSWORD_DIGIT.search(v):
            raise ValueError("Mật khẩu phải có ít nhất 1 chữ số (0-9)")
        return v


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
