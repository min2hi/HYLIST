"""
AuditLog Middleware — Tự động persist mọi state change vào bảng audit_logs.

Thiết kế (Senior pattern):
  - Middleware KHÔNG inject get_db() — tránh circular dependency và performance hit
  - Sau khi response trả về → dùng asyncio.create_task() fire-and-forget
  - DB session riêng biệt cho audit (không ảnh hưởng transaction của request)
  - Fail silently: lỗi audit KHÔNG làm fail request của user

Cách hoạt động:
  POST/PATCH/PUT/DELETE → response 2xx → extract user từ JWT → insert AuditLog
"""

import asyncio
from datetime import UTC, datetime
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
SKIP_PATHS = {"/health", "/metrics", "/", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}


class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    Middleware ghi audit log tự động vào DB.
    Dùng fire-and-forget pattern để không block response.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in AUDITED_METHODS:
            return await call_next(request)

        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        # Decode JWT trước khi call route (token hợp lệ tại thời điểm này)
        user_id: str | None = None
        org_id: str | None = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                )
                user_id = payload.get("sub")
                org_id = payload.get("org_id")
            except JWTError:
                pass  # Route handler sẽ xử lý lỗi auth

        # Gọi route handler
        response = await call_next(request)

        # Chỉ persist nếu thành công (2xx) và có user
        if 200 <= response.status_code < 300 and user_id:
            # Fire-and-forget: không await, không block response
            asyncio.create_task(
                self._persist_audit_log(
                    user_id=user_id,
                    org_id=org_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    ip=request.client.host if request.client else None,
                )
            )

        return response

    async def _persist_audit_log(
        self,
        user_id: str,
        org_id: str | None,
        method: str,
        path: str,
        status_code: int,
        ip: str | None,
    ) -> None:
        """
        Insert audit record vào DB dùng session riêng (không dùng session của request).
        Fail silently — lỗi audit không ảnh hưởng user experience.
        """
        # Import ở đây tránh circular import
        from ..core.database import AsyncSessionLocal
        from ..models import AuditLog

        path_parts = path.strip("/").split("/")
        entity_type: str | None = None
        entity_id: str | None = None

        # Extract entity info từ URL pattern: /api/v1/{resource}/{id}
        resource_names = {"tasks", "projects", "users"}
        for i, part in enumerate(path_parts):
            if part in resource_names:
                entity_type = part.rstrip("s")  # "tasks" → "task"
                if i + 1 < len(path_parts):
                    try:
                        entity_id = str(UUID(path_parts[i + 1]))
                    except (ValueError, AttributeError):
                        pass
                break

        action_map = {
            "POST": "created",
            "PATCH": "updated",
            "PUT": "replaced",
            "DELETE": "deleted",
        }

        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    audit = AuditLog(
                        id=uuid4(),
                        org_id=UUID(org_id) if org_id else uuid4(),  # fallback safe
                        user_id=UUID(user_id),
                        entity_type=entity_type or "unknown",
                        entity_id=UUID(entity_id) if entity_id else uuid4(),
                        action=action_map.get(method, method.lower()),
                        ip_address=ip,
                        timestamp=datetime.now(UTC),
                    )
                    session.add(audit)
        except Exception as exc:
            # Fail silently — log nhưng không raise
            logger.warning(
                "audit_log_persist_failed",
                error=str(exc),
                user_id=user_id,
                path=path,
            )
