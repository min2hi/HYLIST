"""Unit tests — Auth Service."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.schemas.auth import RegisterRequest, LoginRequest
from src.services.auth_service import AuthService
from src.core.security import hash_password


class TestAuthService:

    @pytest.mark.asyncio
    async def test_register_creates_org_and_admin_user(self, db_session):
        """Register tạo cả Org lẫn User ADMIN đầu tiên."""
        service = AuthService(db_session)
        dto = RegisterRequest(
            email="newuser@example.com",
            password="secure_password_123",
            full_name="New User",
            org_name="New Corp",
        )
        result = await service.register(dto)

        assert result.email == "newuser@example.com"
        assert result.role == "admin"
        assert result.org_id is not None

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises(self, db_session, test_user):
        """Đăng ký email đã tồn tại → ValueError."""
        service = AuthService(db_session)
        dto = RegisterRequest(
            email=test_user.email,  # Email đã tồn tại
            password="another_password",
            full_name="Duplicate",
            org_name="Another Corp",
        )
        with pytest.raises(ValueError, match="Email này đã được đăng ký"):
            await service.register(dto)

    @pytest.mark.asyncio
    async def test_login_success(self, db_session, test_user):
        """Login đúng email + password → trả về token."""
        service = AuthService(db_session)
        dto = LoginRequest(email=test_user.email, password="test_password_123")
        result = await service.login(dto)

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password_raises(self, db_session, test_user):
        """Login sai password → ValueError."""
        service = AuthService(db_session)
        dto = LoginRequest(email=test_user.email, password="wrong_password")
        with pytest.raises(ValueError, match="Email hoặc mật khẩu không chính xác"):
            await service.login(dto)

    @pytest.mark.asyncio
    async def test_login_nonexistent_email_raises(self, db_session):
        """Login email không tồn tại → cùng ValueError (anti-enumeration)."""
        service = AuthService(db_session)
        dto = LoginRequest(email="nobody@example.com", password="any_password")
        with pytest.raises(ValueError, match="Email hoặc mật khẩu không chính xác"):
            await service.login(dto)
