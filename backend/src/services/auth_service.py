"""Auth Service — Register + Login logic."""
import re
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Organization, User, UserRole
from ..schemas.auth import LoginRequest, RegisterRequest, TokenData, UserProfile
from ..core.security import hash_password, verify_password, create_access_token, create_refresh_token

logger = structlog.get_logger()


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Register ─────────────────────────────────────────────────────────────
    async def register(self, dto: RegisterRequest) -> UserProfile:
        """
        Tạo Organization mới + Admin user đầu tiên.
        Người đăng ký đầu tiên sẽ là ADMIN của org đó.
        """
        # 1. Kiểm tra email đã tồn tại chưa
        existing = await self.db.execute(select(User).where(User.email == dto.email))
        if existing.scalar_one_or_none():
            raise ValueError("Email này đã được đăng ký")

        # 2. Tạo slug cho org từ tên
        slug = re.sub(r"[^a-z0-9]+", "-", dto.org_name.lower()).strip("-")
        slug_check = await self.db.execute(select(Organization).where(Organization.slug == slug))
        if slug_check.scalar_one_or_none():
            raise ValueError("Tên tổ chức này đã tồn tại, vui lòng chọn tên khác")

        # 3. Tạo Organization
        org = Organization(name=dto.org_name, slug=slug)
        self.db.add(org)
        await self.db.flush()  # Lấy org.id

        # 4. Tạo User ADMIN đầu tiên
        user = User(
            org_id=org.id,
            email=dto.email,
            hashed_password=hash_password(dto.password),
            full_name=dto.full_name,
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        self.db.add(user)
        await self.db.flush()

        logger.info("user_registered", user_id=str(user.id), org_id=str(org.id), email=dto.email)

        return UserProfile(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            org_id=str(user.org_id),
        )

    # ─── Login ────────────────────────────────────────────────────────────────
    async def login(self, dto: LoginRequest) -> TokenData:
        """Xác thực và trả về JWT token."""
        stmt = select(User).where(User.email == dto.email, User.deleted_at.is_(None))
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        # Luôn trả cùng 1 lỗi để tránh user enumeration attack
        if not user or not verify_password(dto.password, user.hashed_password):
            logger.warning("auth_failed", email=dto.email)
            raise ValueError("Email hoặc mật khẩu không chính xác")

        if not user.is_active:
            raise ValueError("Tài khoản đã bị vô hiệu hóa")

        access_token = create_access_token(
            user.id, user.org_id, user.role,
            email=user.email,
            full_name=user.full_name,
        )
        refresh_token = create_refresh_token(user.id)

        logger.info("user_logged_in", user_id=str(user.id), org_id=str(user.org_id))

        return TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
        )
