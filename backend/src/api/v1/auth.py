"""Auth Router — /api/v1/auth/register + /api/v1/auth/login + /api/v1/auth/me"""

import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.security import CurrentUser, get_current_user
from ...schemas.auth import LoginRequest, RegisterRequest, TokenData, UserProfile
from ...schemas.common import SuccessResponse
from ...services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])
limiter = Limiter(key_func=get_remote_address)

_IS_TEST = os.getenv("APP_ENV") == "test"
_REG_LIMIT = "1000/minute" if _IS_TEST else "5/minute"
_LOGIN_LIMIT = "1000/minute" if _IS_TEST else "10/minute"


@router.post(
    "/register", response_model=SuccessResponse[UserProfile], status_code=status.HTTP_201_CREATED
)
@limiter.limit(_REG_LIMIT)
async def register(
    request: Request,
    dto: RegisterRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
):
    """
    Đăng ký tài khoản mới.
    Tự động tạo Workspace (Organization) và cấp quyền ADMIN cho người đăng ký đầu tiên.
    """
    try:
        service = AuthService(db)
        user = await service.register(dto)
        return SuccessResponse(data=user, message="Đăng ký thành công! Chào mừng bạn đến HYLIST.")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.post("/login", response_model=SuccessResponse[TokenData])
@limiter.limit(_LOGIN_LIMIT)
async def login(
    request: Request,
    dto: LoginRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
):
    """Đăng nhập — trả về Access Token và Refresh Token."""
    try:
        service = AuthService(db)
        token = await service.login(dto)
        return SuccessResponse(data=token, message="Đăng nhập thành công")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.get("/me", response_model=SuccessResponse[UserProfile])
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),  # noqa: B008
):
    """Lấy thông tin profile của user đang đăng nhập (từ JWT token)."""
    return SuccessResponse(
        data=UserProfile(
            id=str(current_user.id),
            email=current_user.email,
            full_name=current_user.full_name,
            role=current_user.role,
            org_id=str(current_user.org_id),
        )
    )
