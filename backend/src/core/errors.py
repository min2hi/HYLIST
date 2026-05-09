"""
RFC 7807 Problem Details — Chuẩn hóa error response format.

RFC 7807 (https://www.rfc-editor.org/rfc/rfc7807) là standard được dùng bởi:
  - Stripe: https://stripe.com/docs/api/errors
  - GitHub: https://docs.github.com/en/rest/overview/troubleshooting
  - Shopify: https://shopify.dev/api/usage/response-codes

Format:
  {
    "type":   "URI duy nhat doc lap ve loai loi",
    "title":  "Mo ta ngan, human-readable, KHONG thay doi",
    "status": 422,
    "detail": "Mo ta cu the cho request nay",
    "instance": "/api/v1/tasks/abc123",  # URI cua resource bi loi
    "errors": [...]  # Optional: field-level validation errors
  }

Tai sao tot hon cach cu {success, data, error_code}?
  - Client code co the check 'type' URI de handle cu the
  - Logging va alerting de dang hon (search by type URI)
  - Tuong thich voi OpenAPI 3.1 Problem Details schema
  - Khong phat minh lai the gioi — dung standard da co
"""

from typing import Any

import structlog
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)

# Base URL cho type URIs — thay bang domain thuc khi deploy
_BASE_URL = "https://hylist.io/errors"


# ─── Problem Detail Types (URI constants) ─────────────────────────────────────
# Dung constant de tranh typo va de search trong codebase


class ProblemType:
    # Auth
    UNAUTHORIZED = f"{_BASE_URL}/unauthorized"
    FORBIDDEN = f"{_BASE_URL}/forbidden"
    TOKEN_EXPIRED = f"{_BASE_URL}/token-expired"

    # Resource
    NOT_FOUND = f"{_BASE_URL}/not-found"
    CONFLICT = f"{_BASE_URL}/conflict"
    GONE = f"{_BASE_URL}/gone"

    # Validation
    VALIDATION = f"{_BASE_URL}/validation-error"
    INVALID_INPUT = f"{_BASE_URL}/invalid-input"

    # Rate limiting
    RATE_LIMITED = f"{_BASE_URL}/rate-limited"

    # Server
    INTERNAL = f"{_BASE_URL}/internal-server-error"
    SERVICE_DOWN = f"{_BASE_URL}/service-unavailable"

    # Business logic
    INSUFFICIENT_QUOTA = f"{_BASE_URL}/insufficient-quota"
    ML_UNAVAILABLE = f"{_BASE_URL}/ml-unavailable"


def problem_detail(
    *,
    status_code: int,
    problem_type: str,
    title: str,
    detail: str,
    instance: str | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """
    Tao RFC 7807 Problem Detail response.

    Usage trong router:
        return problem_detail(
            status_code=404,
            problem_type=ProblemType.NOT_FOUND,
            title="Task not found",
            detail=f"Task {task_id} does not exist in org {org_id}",
            instance=f"/api/v1/tasks/{task_id}",
        )
    """
    body: dict[str, Any] = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    if extra:
        body.update(extra)

    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",  # RFC 7807 media type
    )


# ─── Exception Handlers (register vao FastAPI app) ────────────────────────────


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Override default FastAPI HTTPException handler.
    Chuyen {"detail": "..."} thanh RFC 7807 format.
    """
    # Map HTTP status codes to problem types
    type_map = {
        400: ProblemType.INVALID_INPUT,
        401: ProblemType.UNAUTHORIZED,
        403: ProblemType.FORBIDDEN,
        404: ProblemType.NOT_FOUND,
        409: ProblemType.CONFLICT,
        429: ProblemType.RATE_LIMITED,
        503: ProblemType.SERVICE_DOWN,
    }
    title_map = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        503: "Service Unavailable",
    }

    problem_type = type_map.get(exc.status_code, ProblemType.INTERNAL)
    title = title_map.get(exc.status_code, "Error")

    logger.warning(
        "http_exception",
        path=request.url.path,
        status=exc.status_code,
        detail=str(exc.detail),
    )

    return problem_detail(
        status_code=exc.status_code,
        problem_type=problem_type,
        title=title,
        detail=str(exc.detail) if exc.detail else title,
        instance=request.url.path,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Override default 422 validation error handler.
    Flatten Pydantic errors thanh field-level errors array.

    Input (Pydantic default):
      {"detail": [{"loc": ["body", "title"], "msg": "...", "type": "..."}]}

    Output (RFC 7807 + field errors):
      {
        "type": "https://hylist.io/errors/validation-error",
        "title": "Validation Error",
        "status": 422,
        "detail": "Request body contains invalid data",
        "errors": [
          {"field": "title", "message": "Field required", "code": "missing"}
        ]
      }
    """
    field_errors = []
    for err in exc.errors():
        loc = err.get("loc", [])
        # Skip 'body' prefix neu co
        field_parts = [str(p) for p in loc if p != "body"]
        field = ".".join(field_parts) if field_parts else "unknown"
        field_errors.append(
            {
                "field": field,
                "message": err.get("msg", "Invalid value"),
                "code": err.get("type", "validation_error"),
            }
        )

    logger.info(
        "validation_error",
        path=request.url.path,
        errors=field_errors,
    )

    return problem_detail(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        problem_type=ProblemType.VALIDATION,
        title="Validation Error",
        detail="Request body contains invalid data. See 'errors' for details.",
        instance=request.url.path,
        extra={"errors": field_errors},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all cho unhandled exceptions.
    Log day du nhung khong expose internal details cho client.
    """
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        exc_type=type(exc).__name__,
    )
    return problem_detail(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        problem_type=ProblemType.INTERNAL,
        title="Internal Server Error",
        detail="An unexpected error occurred. Our team has been notified.",
        instance=request.url.path,
    )


def register_exception_handlers(app: Any) -> None:
    """
    Register tat ca exception handlers vao FastAPI app.
    Goi trong main.py sau khi tao app instance.

    Usage:
        app = FastAPI(...)
        register_exception_handlers(app)
    """
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    logger.info("exception_handlers_registered", standard="RFC 7807")
