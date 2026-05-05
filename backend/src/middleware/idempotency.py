"""
Idempotency Key Middleware — Chống tạo trùng khi client retry.

Cách hoạt động:
  1. Client gửi POST request kèm header `Idempotency-Key: <uuid>`
  2. Middleware kiểm tra Redis xem key này đã từng thành công chưa
  3. Nếu đã có → trả về response cũ ngay, KHÔNG xử lý lại
  4. Nếu chưa có → cho request đi qua, lưu kết quả vào Redis 24h

Tại sao cần:
  - Mobile app mất mạng, bấm "Tạo Task" 3 lần → sẽ không bị tạo 3 task
  - Đúng chuẩn RFC 7231 idempotency
"""
import json

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = structlog.get_logger()

# Chỉ áp dụng Idempotency cho POST (tạo mới)
IDEMPOTENCY_METHODS = {"POST"}
IDEMPOTENCY_TTL = 86400  # 24 giờ (seconds)
IDEMPOTENCY_HEADER = "Idempotency-Key"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware idempotency — dùng Redis làm cache.
    Nếu Redis không khả dụng → bỏ qua (fail-open), không block request.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Chỉ áp dụng cho POST
        if request.method not in IDEMPOTENCY_METHODS:
            return await call_next(request)

        # Lấy Idempotency-Key từ header
        idem_key = request.headers.get(IDEMPOTENCY_HEADER)
        if not idem_key:
            # Không có key → cho qua bình thường (key là optional)
            return await call_next(request)

        # Tạo cache key có prefix để tránh collision
        cache_key = f"idem:{idem_key}"

        # Thử đọc từ Redis
        try:
            from ..core.redis import redis_client
            cached = await redis_client.get(cache_key)

            if cached:
                # Đã từng tạo thành công → trả về response cũ
                logger.info("idempotency_cache_hit", key=idem_key)
                cached_data = json.loads(cached)
                return JSONResponse(
                    content=cached_data["body"],
                    status_code=cached_data["status_code"],
                    headers={"X-Idempotency-Replayed": "true"},
                )
        except Exception as e:
            # Redis không khả dụng → fail-open, tiếp tục xử lý bình thường
            logger.warning("idempotency_redis_unavailable", error=str(e))
            return await call_next(request)

        # Chưa có cache → xử lý request
        response = await call_next(request)

        # Chỉ cache nếu thành công (2xx)
        if 200 <= response.status_code < 300:
            try:
                # Đọc response body
                body_bytes = b""
                async for chunk in response.body_iterator:
                    body_bytes += chunk

                body = json.loads(body_bytes.decode("utf-8"))

                # Lưu vào Redis
                await redis_client.setex(
                    cache_key,
                    IDEMPOTENCY_TTL,
                    json.dumps({"status_code": response.status_code, "body": body}),
                )
                logger.info("idempotency_cached", key=idem_key, ttl=IDEMPOTENCY_TTL)

                # Trả lại response (body đã đọc hết, cần rebuild)
                return Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
            except Exception as e:
                logger.warning("idempotency_cache_write_failed", error=str(e))

        return response
