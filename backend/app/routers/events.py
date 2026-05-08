"""Server-Sent Events endpoint for the bench TUI log."""
import json
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies import verify_api_key_or_query
from app.services.event_stream import subscribe

router = APIRouter(prefix="/events", tags=["events"])


async def _format_sse() -> AsyncIterator[bytes]:
    async for event in subscribe():
        payload = json.dumps(event)
        yield f"data: {payload}\n\n".encode("utf-8")


@router.get("/stream")
async def stream_events(
    _: str = Depends(verify_api_key_or_query),
) -> StreamingResponse:
    """Stream the event ring buffer + new events to the client.

    Auth: any valid X-API-Key, query-string ?api_key=, or JWT.

    SECURITY NOTES (v1 trade-offs — acceptable for solo-dev / public-demo
    deployments, NOT for multi-tenant production):

    1. Events are NOT user-scoped. Every authenticated client receives every
       event, including project_ids and meta.title strings from other users.
       For multi-tenant use, accept a user_id in subscribe() and filter
       inside the iterator.

    2. The query-string ?api_key= path leaks the secret into reverse-proxy
       access logs (nginx, Cloudflare). It exists because EventSource cannot
       set custom headers. For multi-tenant production, exchange a short-lived
       SSE-only token via POST and pass that as the query param.

    3. No heartbeat — proxies may drop idle SSE connections at 60-100s,
       causing reconnect churn. Future: yield a ': heartbeat\\n\\n' comment
       every 25s.
    """
    return StreamingResponse(
        _format_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
