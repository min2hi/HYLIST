"""
SSE Router — Real-time event streaming (Phase 3, Tuần 11).

Endpoints:
  GET /api/v1/events/stream           → Subscribe toan bo events cua org (board view)
  GET /api/v1/events/task/{task_id}   → Subscribe events cua 1 task cu the (task detail)

Client usage (JavaScript):
  // Org-level stream (Kanban board)
  const es = new EventSource("/api/v1/events/stream", {withCredentials: true})
  es.addEventListener("tags_updated", (e) => updateTaskTag(JSON.parse(e.data)))
  es.addEventListener("prediction_done", (e) => updateTaskPrediction(JSON.parse(e.data)))

  // Task-specific stream (Task detail page)
  const es = new EventSource(`/api/v1/events/task/${taskId}`, {withCredentials: true})
  es.addEventListener("tags_updated", (e) => setTags(JSON.parse(e.data)))

Security:
  - JWT token required (Bearer header OR ?token= query param for EventSource)
  - EventSource API khong ho tro custom headers → dung query param fallback
  - org_id filter dam bao user chi nhan events cua org minh

Limits:
  - Max 50 concurrent SSE connections per IP (rate limiter)
  - Heartbeat 15s → detect disconnect nhanh hon TCP timeout
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from ...core.security import CurrentUser, require_auth_sse
from ...core.sse import CHANNEL_ORG, CHANNEL_TASK, SSEEventBus

router = APIRouter(prefix="/events", tags=["SSE / Real-time"])


@router.get(
    "/stream",
    summary="Org-level SSE stream",
    description="Subscribe to all real-time events for the authenticated user's org.",
    responses={
        200: {"description": "SSE stream — keep-alive connection"},
        401: {"description": "Unauthorized"},
    },
)
async def org_event_stream(
    request: Request,
    current_user: CurrentUser = Depends(require_auth_sse),
) -> EventSourceResponse:
    """
    Org-level SSE stream.
    Client nhan TAT CA events cua org: tags_updated, prediction_done, task_created, v.v.
    Dung cho Kanban board view — update real-time khi bat ky task nao thay doi.
    """
    bus = SSEEventBus.get()
    channel = CHANNEL_ORG.format(org_id=str(current_user.org_id))

    async def _generator():
        # Gui initial connection event
        yield {
            "event": "connected",
            "data": f'{{"org_id": "{current_user.org_id}", "channel": "{channel}"}}',
        }

        async for event in bus.subscribe(channel, request):
            if event.get("event") == "heartbeat":
                # SSE spec: comment line keeps connection alive, khong trigger addEventListener
                yield {"event": "heartbeat", "data": ""}
            else:
                yield {
                    "event": event.get("event", "update"),
                    "data": _serialize(event),
                    "id": event.get("task_id", ""),
                }

    return EventSourceResponse(
        _generator(),
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # Tat nginx/proxy buffering
        },
    )


@router.get(
    "/task/{task_id}",
    summary="Task-specific SSE stream",
    description="Subscribe to real-time events for a specific task.",
)
async def task_event_stream(
    task_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_auth_sse),
) -> EventSourceResponse:
    """
    Task-specific SSE stream.
    Dung cho Task detail page — chi nhan events cua task nay.
    """
    bus = SSEEventBus.get()
    channel = CHANNEL_TASK.format(task_id=task_id)

    async def _generator():
        yield {
            "event": "connected",
            "data": f'{{"task_id": "{task_id}"}}',
        }

        async for event in bus.subscribe(channel, request):
            if event.get("event") == "heartbeat":
                yield {"event": "heartbeat", "data": ""}
            else:
                yield {
                    "event": event.get("event", "update"),
                    "data": _serialize(event),
                    "id": event.get("task_id", task_id),
                }

    return EventSourceResponse(
        _generator(),
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/health",
    summary="SSE Bus health check",
    tags=["health"],
)
async def sse_health() -> JSONResponse:
    """Check SSE event bus status — so luong subscribers hien tai."""
    try:
        bus = SSEEventBus.get()
        subscriber_count = sum(len(q) for q in bus._subscribers.values())
        channel_count = len(bus._subscribers)
        return JSONResponse(
            {
                "status": "ok",
                "channels": channel_count,
                "subscribers": subscriber_count,
            }
        )
    except RuntimeError:
        return JSONResponse({"status": "not_initialized"}, status_code=503)


def _serialize(event: dict) -> str:
    """Serialize event data to JSON string cho SSE data field."""
    import json

    data = event.get("data", event)
    if isinstance(data, dict):
        return json.dumps(data)
    return str(data)
