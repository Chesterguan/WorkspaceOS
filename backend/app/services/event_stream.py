"""In-memory event ring buffer + emit helper for the bench TUI log.

Events are ephemeral runtime telemetry — NOT an audit log. The buffer
holds the last 200 events; older ones are evicted. SSE consumers replay
the buffer on connect, then receive new events as they're emitted.

See docs/superpowers/plans/2026-05-06-bench-ui.md
"""
import asyncio
import json
import logging
import time
import uuid
from collections import deque
from typing import Any, AsyncIterator, Deque, Dict, Optional

logger = logging.getLogger(__name__)

BUFFER_LIMIT = 200
_VALID_LEVELS = frozenset({"info", "success", "warn", "error"})

_buffer: Deque[Dict[str, Any]] = deque(maxlen=BUFFER_LIMIT)
_subscribers: list[asyncio.Queue] = []
_subscribers_lock = asyncio.Lock()


def emit(
    level: str,
    source: str,
    summary: str,
    project_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit an event to the buffer and broadcast to all SSE subscribers.

    Synchronous — safe to call from any sync or async context. Subscriber
    fan-out is fire-and-forget via asyncio task scheduling.
    """
    if level not in _VALID_LEVELS:
        level = "info"
    event = {
        "ts": time.time(),
        "level": level,
        "source": source,
        "summary": summary[:200],
        "project_id": str(project_id) if project_id else None,
        "meta": meta or {},
    }
    _buffer.append(event)
    # Fan out to subscribers without blocking; missed deliveries are acceptable
    # (TUI log is best-effort telemetry, not durable).
    try:
        loop = asyncio.get_running_loop()
        for q in list(_subscribers):
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except Exception:
                pass
    except RuntimeError:
        # No running loop (e.g., emit called from a sync context). Buffer
        # already updated; the next subscriber connect will replay it.
        pass


def get_buffer() -> list[Dict[str, Any]]:
    """Return a snapshot copy of the current buffer (oldest → newest)."""
    return list(_buffer)


async def subscribe() -> AsyncIterator[Dict[str, Any]]:
    """Async iterator yielding buffered + live events for an SSE consumer.

    Race-free contract: register the subscriber queue BEFORE replaying the
    buffer. This ensures events emitted concurrently with the subscribe()
    call land in the queue exactly once — either via the buffer replay
    (if they were already there) or via fan-out (if they happened after).
    Worst case: an event in the buffer is also delivered live, producing a
    duplicate. The consumer is responsible for de-duping if it cares.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    # Register first so any concurrent emit() reaches us before we replay.
    async with _subscribers_lock:
        _subscribers.append(queue)

    try:
        # Replay current buffer state. Events appended between these two
        # operations may be delivered twice (once via fan-out, once via this
        # replay) — acceptable; consumers can dedupe by ts+source+summary.
        for event in get_buffer():
            await queue.put(event)

        while True:
            event = await queue.get()
            yield event
    finally:
        async with _subscribers_lock:
            try:
                _subscribers.remove(queue)
            except ValueError:
                pass
