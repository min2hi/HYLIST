"""Integration tests — Auth API endpoints."""
import uuid
import pytest
from httpx import AsyncClient


def unique_email(prefix: str = "user") -> str:
    """Tạo email unique để tránh conflict giữa các test."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


class TestAuthRegister:

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """POST /auth/register → 201 với user data."""
        response = await client.post("/api/v1/auth/register", json={
            "email": unique_email("register"),
            "password": "SecurePass123",
            "full_name": "Integration User",
            "org_name": f"Corp-{uuid.uuid4().hex[:6]}",
        })
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["success"] is True
        assert data["data"]["role"] == "admin"

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """POST /auth/register với email không hợp lệ → 422."""
        response = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "SecurePass123",
            "full_name": "Test",
            "org_name": "Test Corp",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_password_too_short(self, client: AsyncClient):
        """POST /auth/register với password < 8 ký tự → 422."""
        response = await client.post("/api/v1/auth/register", json={
            "email": unique_email(),
            "password": "123",
            "full_name": "Test",
            "org_name": "Test Corp",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_fields(self, client: AsyncClient):
        """POST /auth/register thiếu field bắt buộc → 422."""
        response = await client.post("/api/v1/auth/register", json={
            "email": unique_email(),
        })
        assert response.status_code == 422


class TestAuthLogin:

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient):
        """POST /auth/login với đúng credentials → 200 + tokens."""
        email = unique_email("login")
        org = f"login-corp-{uuid.uuid4().hex[:6]}"
        password = "SecurePass123"

        # Tạo tài khoản trước
        reg = await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "full_name": "Login User",
            "org_name": org,
        })
        assert reg.status_code == 201

        # Đăng nhập
        response = await client.post("/api/v1/auth/login", json={
            "email": email,
            "password": password,
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, client: AsyncClient):
        """POST /auth/login thiếu password → 422."""
        response = await client.post("/api/v1/auth/login", json={
            "email": unique_email(),
        })
        assert response.status_code == 422


class TestAuthMe:

    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, client: AsyncClient):
        """GET /auth/me với token hợp lệ → 200 + profile."""
        email = unique_email("me")
        org = f"me-corp-{uuid.uuid4().hex[:6]}"
        password = "SecurePass123"

        # Tạo tài khoản và lấy token
        await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": password,
            "full_name": "Me User",
            "org_name": org,
        })
        login = await client.post("/api/v1/auth/login", json={
            "email": email, "password": password,
        })
        token = login.json()["data"]["access_token"]

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["data"]["email"] == email
        assert data["data"]["role"] == "admin"

    @pytest.mark.asyncio
    async def test_me_without_token(self, client: AsyncClient):
        """GET /auth/me không có token → 401 hoặc 403."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in (401, 403)
