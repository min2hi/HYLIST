"""
Redis client — dùng cho:
  - Cache: lưu kết quả query tốn kém
  - Idempotency: tránh duplicate requests
  - Celery broker: queue NLP/Agent tasks
  - Pub/Sub: trigger SSE events
  - Session store: refresh tokens
"""
from redis.asyncio import Redis, ConnectionPool
from .config import settings

# Connection pool — tái sử dụng connections
_pool: ConnectionPool = ConnectionPool.from_url(
    settings.REDIS_URL,
    max_connections=20,
    decode_responses=True,  # Trả về str thay vì bytes
)

# Client singleton
redis_client: Redis = Redis(connection_pool=_pool)


async def get_redis() -> Redis:
    """FastAPI Dependency — inject Redis vào Router nếu cần."""
    return redis_client


# ─── Helper functions ───────────────────────────────────────────────────────────

async def cache_set(key: str, value: str, ttl_seconds: int = 300) -> None:
    """Lưu giá trị vào cache với TTL."""
    await redis_client.setex(key, ttl_seconds, value)


async def cache_get(key: str) -> str | None:
    """Lấy giá trị từ cache. Trả về None nếu miss."""
    return await redis_client.get(key)


async def cache_delete(key: str) -> None:
    """Xóa một key khỏi cache."""
    await redis_client.delete(key)


async def publish_event(channel: str, message: str) -> None:
    """Publish SSE event qua Redis Pub/Sub.
    
    Dùng:
        await publish_event(f"task:{task_id}:tags_updated", json.dumps(tags))
    """
    await redis_client.publish(channel, message)
