"""
JWT Authentication + Password hashing.

Flow:
  1. User login → verify password → tạo access_token + refresh_token
  2. Mọi request protected → Authorization: Bearer <token>
  3. get_current_user() decode token → lấy user info
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import settings

# JWT bearer scheme
bearer_scheme = HTTPBearer()


# ─── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash mật khẩu trước khi lưu DB. Không lưu plain text."""
    salt = bcrypt.gensalt()
    # Chuyển đổi thành bytes, băm, rồi decode lại thành chuỗi utf-8 để lưu DB
    hashed = bcrypt.hashpw(plain.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """So sánh mật khẩu nhập vào với hash trong DB."""
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


# ─── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(user_id: UUID, org_id: UUID, role: str, email: str = "", full_name: str = "") -> str:
    """Tạo JWT access token có thời hạn."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "email": email,
        "full_name": full_name,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """Tạo refresh token dài hạn hơn."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ─── Current User Dependency ────────────────────────────────────────────────────

class CurrentUser:
    """Object đại diện user đã xác thực — inject qua Depends(get_current_user)."""
    def __init__(self, id: UUID, org_id: UUID, role: str, email: str = "", full_name: str = ""):
        self.id = id
        self.org_id = org_id
        self.role = role
        self.email = email
        self.full_name = full_name


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    """
    FastAPI Dependency — decode JWT và trả về CurrentUser.
    
    Dùng:
        @router.get("/tasks")
        async def get_tasks(user: CurrentUser = Depends(get_current_user)):
            # user.id, user.org_id, user.role
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token không hợp lệ hoặc đã hết hạn",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        org_id: str | None = payload.get("org_id")
        role: str | None = payload.get("role")
        token_type: str | None = payload.get("type")

        if not user_id or not org_id or not role or token_type != "access":
            raise credentials_exception

        email: str = payload.get("email", "")
        full_name: str = payload.get("full_name", "")

    except JWTError:
        raise credentials_exception

    return CurrentUser(
        id=UUID(user_id),
        org_id=UUID(org_id),
        role=role,
        email=email,
        full_name=full_name,
    )
