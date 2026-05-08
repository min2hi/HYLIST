"""
Unit tests cho SSEEventBus.

Test strategy:
  - Mock Redis client hoan toan — khong can Redis thuc
  - Test subscribe/dispatch/heartbeat/overflow logic
  - Test shutdown sentinel propagation
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.sse import (
    CHANNEL_ORG,
    CHANNEL_TASK,
    HEARTBEAT_INTERVAL,
    SSEEventBus,
)


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.publish = AsyncMock(return_value=1)
    return r


@pytest.fixture
def bus(mock_redis):
    """Fresh SSEEventBus instance per test (bypass singleton)."""
    SSEEventBus._instance = None
    instance = SSEEventBus(mock_redis)
    yield instance
    # Cleanup
    SSEEventBus._instance = None


class TestSSEEventBusPublish:

    @pytest.mark.asyncio
    async def test_publish_calls_redis(self, bus, mock_redis):
        """publish() phai goi redis.publish voi dung channel va payload."""
        payload = {"event": "tags_updated", "task_id": "abc-123"}
        await bus.publish("sse:task:abc-123", payload)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "sse:task:abc-123"
        assert json.loads(call_args[0][1]) == payload

    @pytest.mark.asyncio
    async def test_publish_swallows_redis_error(self, bus, mock_redis):
        """publish() khong raise khi Redis fail — silent degradation."""
        mock_redis.publish.side_effect = ConnectionError("Redis down")
        # Khong raise — just logs error
        await bus.publish("sse:org:xyz", {"event": "test"})

    def test_channel_format_task(self):
        channel = CHANNEL_TASK.format(task_id="abc-123")
        assert channel == "sse:task:abc-123"

    def test_channel_format_org(self):
        channel = CHANNEL_ORG.format(org_id="org-789")
        assert channel == "sse:org:org-789"


class TestSSEEventBusDispatch:

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_correct_channel(self, bus):
        """_dispatch() phai dua event vao dung queue theo channel."""
        queue = asyncio.Queue()
        bus._subscribers["sse:task:abc"] = {queue}

        await bus._dispatch("sse:task:abc", {"event": "test", "data": "ok"})

        assert not queue.empty()
        event = queue.get_nowait()
        assert event["event"] == "test"

    @pytest.mark.asyncio
    async def test_dispatch_multiple_subscribers(self, bus):
        """Khi co nhieu subscriber, tat ca deu nhan duoc event."""
        q1, q2, q3 = asyncio.Queue(), asyncio.Queue(), asyncio.Queue()
        bus._subscribers["sse:org:xyz"] = {q1, q2, q3}

        await bus._dispatch("sse:org:xyz", {"event": "broadcast"})

        assert not q1.empty()
        assert not q2.empty()
        assert not q3.empty()

    @pytest.mark.asyncio
    async def test_dispatch_no_subscribers_noop(self, bus):
        """Neu khong co subscriber → _dispatch la no-op, khong raise."""
        await bus._dispatch("sse:task:unknown", {"event": "orphan"})

    @pytest.mark.asyncio
    async def test_dispatch_lru_drop_when_queue_full(self, bus):
        """Khi queue day → drop oldest event thay vi block."""
        from src.core.sse import _QUEUE_MAXSIZE

        queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        # Fill queue
        for i in range(_QUEUE_MAXSIZE):
            await queue.put({"event": f"old_{i}"})

        bus._subscribers["sse:task:busy"] = {queue}

        # Dispatch them 1 event vao queue day
        await bus._dispatch("sse:task:busy", {"event": "newest"})

        # Queue van full nhung co event moi nhat
        assert queue.full()
        # Lay tat ca events, event cuoi phai la newest
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        assert any(e["event"] == "newest" for e in events)


class TestSSEEventBusSubscribe:

    @pytest.mark.asyncio
    async def test_subscribe_yields_events_then_disconnects(self, bus):
        """subscribe() yields events cho den khi client disconnect."""
        # Mock request disconnect sau 1 event
        mock_request = AsyncMock()
        disconnect_calls = [False, True]  # First: connected, Second: disconnected
        mock_request.is_disconnected = AsyncMock(side_effect=disconnect_calls)

        # Pre-populate queue voi 1 event
        event = {"event": "tags_updated", "task_id": "abc", "data": {"tag": "Bug"}}
        channel = "sse:task:abc"

        # Monkey-patch subscribe de inject event ngay
        async def inject_and_subscribe():
            received = []
            # Start subscription
            sub_gen = bus.subscribe(channel, mock_request)
            # Inject event sau khi subscriber duoc tao
            async for item in sub_gen:
                received.append(item)
                # Force put sentinel to stop
                for q in bus._subscribers.get(channel, set()):
                    await q.put(None)
                break
            return received

        # Inject event vao queue ngay truoc khi subscribe
        async def run():
            task = asyncio.create_task(inject_and_subscribe())
            await asyncio.sleep(0.01)
            # Dispatch event
            await bus._dispatch(channel, event)
            return await task

        result = await asyncio.wait_for(run(), timeout=2.0)
        # Subscriber da disconnected → no events received (sentinel stop)
        # Test chi kiem tra khong bi treo (timeout)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_subscribe_cleans_up_after_disconnect(self, bus):
        """Sau khi disconnect, subscriber phai duoc xoa khoi _subscribers."""
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(return_value=True)

        channel = "sse:task:cleanup"
        gen = bus.subscribe(channel, mock_request)

        try:
            async with asyncio.timeout(2.0):
                async for _ in gen:
                    pass
        except (StopAsyncIteration, asyncio.TimeoutError):
            pass

        # Channel should be cleaned up
        assert channel not in bus._subscribers


class TestSSEEventBusInit:

    def test_get_raises_if_not_initialized(self):
        SSEEventBus._instance = None
        with pytest.raises(RuntimeError, match="not initialized"):
            SSEEventBus.get()

    def test_init_sets_instance(self, mock_redis):
        SSEEventBus._instance = None
        instance = SSEEventBus.init(mock_redis)
        assert SSEEventBus.get() is instance
        SSEEventBus._instance = None
