"""
SSE Event Bus — Redis Pub/Sub bridge cho Server-Sent Events.

Architecture:
  NLP/ML Worker → publish(channel, payload)
        ↓ Redis Pub/Sub
  SSE EventBus → subscribe(channel) → AsyncGenerator
        ↓
  SSE Router → EventSourceResponse → Browser

Design decisions:
  - Dùng Redis Pub/Sub (KHÔNG dùng Redis Streams) vi don gian hon
    va SSE la per-connection, khong can consumer groups
  - Channel naming: "sse:org:{org_id}"  → moi browser tab cua org nhan tat ca events
                    "sse:task:{task_id}" → chỉ cập nhật task cu the
  - Backpressure: asyncio.Queue(maxsize=100) per subscriber
    neu queue day (client cham) → drop oldest event (LRU) thay vi block
  - Heartbeat: 15s ping de giu connection song va detect disconnects
  - Reconnect: client dung EventSource API tu dong retry sau 3s
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

# Channel prefixes — tach biet event types
CHANNEL_ORG = "sse:org:{org_id}"  # Broadcast toan org
CHANNEL_TASK = "sse:task:{task_id}"  # Task-specific update

# Heartbeat interval (seconds) — giu WebSocket/SSE song qua proxies
HEARTBEAT_INTERVAL = 15

# Max events buffered per subscriber truoc khi drop
_QUEUE_MAXSIZE = 100


class SSEEventBus:
    """
    Singleton event bus bridging Redis Pub/Sub → AsyncGenerator per SSE connection.

    Usage:
        bus = SSEEventBus.get()
        async for event in bus.subscribe("sse:org:123", request):
            yield event
    """

    _instance: "SSEEventBus | None" = None

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        # channel → set of subscriber queues
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._pubsub_task: asyncio.Task | None = None

    @classmethod
    def get(cls) -> "SSEEventBus":
        if cls._instance is None:
            raise RuntimeError("SSEEventBus not initialized. Call SSEEventBus.init() first.")
        return cls._instance

    @classmethod
    def init(cls, redis: Redis) -> "SSEEventBus":
        cls._instance = cls(redis)
        return cls._instance

    async def start(self) -> None:
        """Start background Redis Pub/Sub listener."""
        if self._pubsub_task is None or self._pubsub_task.done():
            self._pubsub_task = asyncio.create_task(
                self._redis_listener(), name="sse_redis_listener"
            )
            logger.info("sse_event_bus_started")

    async def stop(self) -> None:
        """Graceful shutdown — cancel listener, drain subscribers."""
        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
        # Notify all subscribers that the bus is shutting down
        for queues in self._subscribers.values():
            for q in queues:
                await q.put(None)  # Sentinel to stop generators
        logger.info("sse_event_bus_stopped")

    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """
        Publish event to channel.
        Called by: NLP worker, ML worker, and API endpoints directly.
        """
        try:
            await self._redis.publish(channel, json.dumps(payload))
            logger.debug("sse_published", channel=channel, event=payload.get("event"))
        except Exception as e:
            logger.error("sse_publish_failed", channel=channel, error=str(e))

    async def subscribe(
        self,
        channel: str,
        request: Any,  # starlette.requests.Request
    ) -> AsyncGenerator[dict, None]:
        """
        Subscribe to a channel. Returns async generator of SSE events.
        Automatically unsubscribes when client disconnects.

        Usage:
            async for event in bus.subscribe("sse:org:abc", request):
                yield event
        """
        queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)

        if channel not in self._subscribers:
            self._subscribers[channel] = set()
            # Subscribe channel in Redis when first subscriber arrives
            await self._ensure_subscribed(channel)

        self._subscribers[channel].add(queue)
        subscriber_count = len(self._subscribers[channel])
        logger.info(
            "sse_client_connected",
            channel=channel,
            subscribers=subscriber_count,
        )

        try:
            while True:
                # Check client disconnect
                if await request.is_disconnected():
                    logger.info("sse_client_disconnected", channel=channel)
                    break

                try:
                    # Wait for event with heartbeat timeout
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)

                    if event is None:  # Shutdown sentinel
                        break

                    yield event

                except TimeoutError:
                    # No event — send heartbeat to keep connection alive
                    yield {"event": "heartbeat", "data": ""}

        finally:
            self._subscribers[channel].discard(queue)
            if not self._subscribers[channel]:
                del self._subscribers[channel]
            logger.info("sse_subscriber_removed", channel=channel)

    async def _ensure_subscribed(self, channel: str) -> None:
        """Tell Redis pubsub to subscribe to this channel pattern."""
        # The listener task handles all channels via psubscribe("sse:*")
        # This is a no-op since we use pattern subscription
        pass

    async def _redis_listener(self) -> None:
        """
        Background task: listen to ALL sse:* channels via pattern subscription.
        Route received messages to correct subscriber queues.
        """
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("sse:*")
        logger.info("sse_redis_psubscribe_started", pattern="sse:*")

        try:
            async for raw in pubsub.listen():
                if raw["type"] not in ("pmessage", "message"):
                    continue

                channel = raw.get("channel", b"")
                if isinstance(channel, bytes):
                    channel = channel.decode()

                data = raw.get("data", b"")
                if isinstance(data, bytes):
                    data = data.decode()

                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue

                await self._dispatch(channel, payload)

        except asyncio.CancelledError:
            logger.info("sse_redis_listener_cancelled")
        except Exception as e:
            logger.error("sse_redis_listener_error", error=str(e))
        finally:
            await pubsub.punsubscribe("sse:*")
            await pubsub.close()

    async def _dispatch(self, channel: str, payload: dict) -> None:
        """Dispatch event to all subscribers of this channel."""
        queues = self._subscribers.get(channel, set()).copy()

        if not queues:
            return

        for queue in queues:
            try:
                if queue.full():
                    # LRU drop: discard oldest to make room
                    try:
                        queue.get_nowait()
                        logger.warning("sse_queue_overflow_drop", channel=channel)
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(payload)
            except Exception as e:
                logger.warning("sse_dispatch_error", channel=channel, error=str(e))


# ── Convenience publish helpers ────────────────────────────────────────────────


async def publish_tags_updated(
    redis: Redis,
    *,
    task_id: str,
    org_id: str,
    tag: str,
    confidence: float,
) -> None:
    """Publish 'tags_updated' event khi NLP worker hoan thanh."""
    payload = {
        "event": "tags_updated",
        "task_id": task_id,
        "data": {"tag": tag, "confidence": round(confidence, 3)},
    }
    # Publish to BOTH channels — org-wide AND task-specific
    await redis.publish(CHANNEL_TASK.format(task_id=task_id), json.dumps(payload))
    await redis.publish(CHANNEL_ORG.format(org_id=org_id), json.dumps(payload))


async def publish_prediction_done(
    redis: Redis,
    *,
    task_id: str,
    org_id: str,
    predicted_hours: float,
    confidence: float,
    fallback: bool,
) -> None:
    """Publish 'prediction_done' event khi ML worker hoan thanh."""
    payload = {
        "event": "prediction_done",
        "task_id": task_id,
        "data": {
            "predicted_hours": round(predicted_hours, 2),
            "confidence": round(confidence, 3),
            "fallback": fallback,
        },
    }
    await redis.publish(CHANNEL_TASK.format(task_id=task_id), json.dumps(payload))
    await redis.publish(CHANNEL_ORG.format(org_id=org_id), json.dumps(payload))
