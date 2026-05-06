"""Unit tests — Auth Service."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.schemas.auth import RegisterRequest, LoginRequest
from src.services.auth_service import AuthService
from src.core.security import hash_password
from src.models import User, Organization


class TestAuthService:

    @pytest.mark.asyncio
    async def test_register_creates_org_and_admin_user(self):
        """Register tạo cả Org lẫn User ADMIN đầu tiên."""
        db = AsyncMock()
        
        # Mock execute for email check (return None means not found)
        # Mock execute for slug check (return None means not found)
        # We need to return an object that has scalar_one_or_none() -> None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        
        added_objects = []
        db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        
        async def mock_flush():
            # simulate DB generating IDs
            for obj in added_objects:
                if not getattr(obj, "id", None):
                    obj.id = uuid.uuid4()
                    
        db.flush = mock_flush

        service = AuthService(db)
        dto = RegisterRequest(
            email="newuser@example.com",
            password="SecurePass123",
            full_name="New User",
            org_name="New Corp",
        )
        result = await service.register(dto)

        assert result.email == "newuser@example.com"
        assert result.role == "admin"
        assert result.org_id is not None
        assert len(added_objects) == 2  # Org and User
        assert isinstance(added_objects[0], Organization)
        assert isinstance(added_objects[1], User)

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises(self):
        """Đăng ký email đã tồn tại → ValueError."""
        db = AsyncMock()
        
        # Mock email already exists
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = User(email="duplicate@example.com")
        db.execute = AsyncMock(return_value=mock_result)
        
        service = AuthService(db)
        dto = RegisterRequest(
            email="duplicate@example.com",
            password="AnotherPass1",
            full_name="Duplicate",
            org_name="Another Corp",
        )
        with pytest.raises(ValueError, match="Email này đã được đăng ký"):
            await service.register(dto)

    @pytest.mark.asyncio
    @patch("src.services.auth_service.verify_password")
    async def test_login_success(self, mock_verify):
        """Login đúng email + password → trả về token."""
        mock_verify.return_value = True
        
        db = AsyncMock()
        user = User(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            email="user@example.com",
            hashed_password="hashed",
            role="admin",
            is_active=True,
            full_name="Test User",
        )
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=mock_result)

        service = AuthService(db)
        dto = LoginRequest(email="user@example.com", password="password")
        result = await service.login(dto)

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"

    @pytest.mark.asyncio
    @patch("src.services.auth_service.verify_password")
    async def test_login_wrong_password_raises(self, mock_verify):
        """Login sai password → ValueError."""
        mock_verify.return_value = False
        
        db = AsyncMock()
        user = User(
            email="user@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=mock_result)

        service = AuthService(db)
        dto = LoginRequest(email="user@example.com", password="wrong_password")
        with pytest.raises(ValueError, match="Email hoặc mật khẩu không chính xác"):
            await service.login(dto)

    @pytest.mark.asyncio
    async def test_login_nonexistent_email_raises(self):
        """Login email không tồn tại → cùng ValueError (anti-enumeration)."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        service = AuthService(db)
        dto = LoginRequest(email="nobody@example.com", password="any_password")
        with pytest.raises(ValueError, match="Email hoặc mật khẩu không chính xác"):
            await service.login(dto)
