"""Server-Sent Events endpoint for the bench TUI log."""
import json
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies import verify_api_key
from app.services.event_stream import subscribe

router = APIRouter(prefix="/events", tags=["events"])


async def _format_sse() -> AsyncIterator[bytes]:
    async for event in subscribe():
        payload = json.dumps(event)
        yield f"data: {payload}\n\n".encode("utf-8")


@router.get("/stream")
async def stream_events(
    _: str = Depends(verify_api_key),
) -> StreamingResponse:
    """Stream the event ring buffer + new events to the client.

    Auth: any valid X-API-Key or JWT. Events are NOT user-scoped in v1
    (single-user dev tool); a future iteration can add per-user filtering.
    """
    return StreamingResponse(
        _format_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
