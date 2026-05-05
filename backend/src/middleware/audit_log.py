"""
AuditLog Middleware — Tự động ghi log mọi thay đổi (POST/PATCH/DELETE).

Cách hoạt động:
  1. Request vào → middleware chặn lại
  2. Nếu là method thay đổi dữ liệu (POST/PATCH/DELETE) → ghi vào bảng audit_logs
  3. Chỉ ghi khi response thành công (2xx)
  4. Không cần gọi thủ công trong Service
"""
import json
from uuid import UUID, uuid4

import structlog
from fastapi import Request, Response
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..core.config import settings

logger = structlog.get_logger()

# Chỉ ghi audit cho các method thay đổi dữ liệu
AUDITED_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

# Bỏ qua các path hệ thống
SKIP_PATHS = {"/health", "/metrics", "/", "/docs", "/openapi.json", "/redoc"}


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Middleware ghi audit log tự động.
    Inject vào app một lần, hoạt động cho mọi router.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Bỏ qua nếu không phải method cần audit
        if request.method not in AUDITED_METHODS:
            return await call_next(request)

        # Bỏ qua system paths
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        # Extract user info từ JWT token (nếu có)
        user_id: str | None = None
        org_id: str | None = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM]
                )
                user_id = payload.get("sub")
                org_id = payload.get("org_id")
            except JWTError:
                pass  # Token invalid — bỏ qua, route handler sẽ xử lý

        # Gọi route handler
        response = await call_next(request)

        # Chỉ ghi log nếu thành công (2xx)
        if 200 <= response.status_code < 300 and user_id:
            await self._write_audit_log(
                request=request,
                response=response,
                user_id=user_id,
                org_id=org_id,
            )

        return response

    async def _write_audit_log(
        self,
        request: Request,
        response: Response,
        user_id: str,
        org_id: str | None,
    ) -> None:
        """Ghi audit log vào structured logger (sau này có thể persist vào DB)."""
        path_parts = request.url.path.strip("/").split("/")

        # Extract entity_type và entity_id từ URL
        # VD: /api/v1/tasks/{id} → entity_type=tasks, entity_id={id}
        entity_type = None
        entity_id = None

        for i, part in enumerate(path_parts):
            if part in ("tasks", "projects", "users"):
                entity_type = part
                if i + 1 < len(path_parts):
                    try:
                        entity_id = str(UUID(path_parts[i + 1]))
                    except (ValueError, AttributeError):
                        pass
                break

        action_map = {
            "POST": "created",
            "PATCH": "updated",
            "PUT": "updated",
            "DELETE": "deleted",
        }

        logger.info(
            "audit_log",
            user_id=user_id,
            org_id=org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action_map.get(request.method, request.method.lower()),
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            ip=request.client.host if request.client else None,
        )
