"""
Per-project activity feed — the one call every emit site makes.

Design rules (kept deliberately small):

  * log_event never raises. Activity logging is diagnostic; a broken log
    must not break the real operation that emitted it. Failures are caught
    and surfaced via the logger, not the call stack.

  * The caller owns commit discipline. We only flush() so the row has an
    id for the caller to pass forward; committing stays with the request
    transaction so the event is visible iff the operation itself lands.

  * Shape is intentionally loose — event_type is a dotted string, details
    is JSONB. New event kinds do not require a migration; the frontend
    renders unknown types with a generic icon.

See migration 0016 for the table definition and the overall rationale.
"""
import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityEvent

logger = logging.getLogger(__name__)


# Allowed source categories. Kept in code rather than the DB so new ones
# don't require a migration — we validate here to catch typos at emit
# time rather than in the feed renderer.
_SOURCES = {"sync", "user", "ai", "ingest", "publish", "system"}


async def log_event(
    db: AsyncSession,
    project_id: uuid.UUID,
    event_type: str,
    summary: str,
    *,
    user_id: Optional[uuid.UUID] = None,
    source: str = "system",
    details: Optional[Dict[str, Any]] = None,
) -> Optional[ActivityEvent]:
    """
    Record one activity event for a project. Returns the created row on
    success, or None if the insert failed (and was swallowed).

    Parameters:
        event_type  Dotted path like "sync.completed" / "worklog.generated".
                    Free-form; no registry — add new ones as needed.
        summary     Short human-readable sentence the UI renders directly.
                    Kept under 500 chars by the column constraint; truncate
                    here too so we never 22001 the caller.
        source      Coarse category ("sync" | "user" | "ai" | "ingest" |
                    "publish" | "system"). Unknown values are coerced to
                    "system" with a warning — forward-compat for typos.
        details     Structured payload (entity ids, counts, durations).
                    Must be JSON-serialisable; the model column is JSONB.
    """
    if source not in _SOURCES:
        logger.warning("activity: unknown source %r, coercing to 'system'", source)
        source = "system"

    # Column caps protect us but we truncate at the boundary so the caller
    # never has to think about it and we never 500 a real endpoint.
    safe_summary = (summary or "").strip()[:500] or "(no summary)"
    safe_event_type = (event_type or "").strip()[:50] or "unknown"

    try:
        entry = ActivityEvent(
            project_id=project_id,
            user_id=user_id,
            event_type=safe_event_type,
            summary=safe_summary,
            details=details,
            source=source,
        )
        db.add(entry)
        await db.flush()
        return entry
    except Exception as exc:  # noqa: BLE001 — logging must never raise
        logger.warning(
            "activity: log_event failed for project=%s event=%s: %s",
            project_id, safe_event_type, exc,
        )
        return None


async def list_events(
    db: AsyncSession,
    project_id: uuid.UUID,
    limit: int = 50,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return the project's activity feed, newest first, with opaque cursor
    pagination. `cursor` is the ISO-8601 `created_at` of the last item the
    caller saw; we return events strictly older than that.

    Limit is clamped to [1, 100] — the feed UI asks for 50, background
    exports might ask for 100, nobody needs 1000 (paginate instead).
    """
    bounded_limit = max(1, min(int(limit or 50), 100))

    query = (
        select(ActivityEvent)
        .where(ActivityEvent.project_id == project_id)
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .limit(bounded_limit + 1)  # fetch one extra to know if there's more
    )
    if cursor:
        from datetime import datetime
        # Clients that embed the cursor straight into a URL without encoding
        # lose the "+" in "+00:00" to a space during URL decoding; normalise
        # that back before parsing so naive callers don't silently get the
        # unfiltered feed.
        normalized = cursor.strip()
        if " " in normalized and "T" in normalized:
            normalized = normalized.replace(" ", "+", 1) if normalized.count(" ") == 1 else normalized.replace(" 00:", "+00:", 1)
        try:
            cursor_dt = datetime.fromisoformat(normalized)
            query = query.where(ActivityEvent.created_at < cursor_dt)
        except ValueError:
            # Bad cursor: treat as "start from newest" rather than 4xx —
            # the feed should degrade gracefully rather than break on a
            # stale client-side bookmark.
            logger.debug("activity: invalid cursor %r; ignoring", cursor)

    rows = (await db.execute(query)).scalars().all()
    has_more = len(rows) > bounded_limit
    items = list(rows[:bounded_limit])
    next_cursor = items[-1].created_at.isoformat() if has_more and items else None

    return {"items": items, "next_cursor": next_cursor}
