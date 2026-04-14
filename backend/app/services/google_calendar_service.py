"""
Google Calendar ingest — pull recent events, classify into projects,
store as memory entries + emit activity events.

Scope for v1:
  * Primary calendar only.
  * Window: 7 days in the past → 14 days in the future (covers "what did
    I just do" and "what's coming up", keeps per-run cost bounded).
  * Dedupe by source_ref = f"gcal:{event_id}" so re-running is idempotent.
    Updating existing events (same id, changed title/time) is v2 — for
    now we skip any item we've seen before.
  * Emits ONE `ingest.calendar` activity event per newly stored item.
    The `memory.added` event is suppressed here by using a source_ref
    that flags this pipeline and letting the feed dedupe by event_type.

Not in scope: attendee email lookups, recurring-event expansion past
the window, private/ACL'd calendars, push notifications.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.services import classifier_service, google_oauth_service
from app.services.activity_service import log_event

logger = logging.getLogger(__name__)

CALENDAR_ENTRY_TYPE = "calendar_event"
SOURCE_PREFIX = "gcal:"

PAST_WINDOW_DAYS = 7
FUTURE_WINDOW_DAYS = 14
MAX_EVENTS = 100  # per run, per user — hard cap so a flood doesn't wreck us


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------

def _format_event_text(event: Dict[str, Any]) -> str:
    """Render the event into a compact text blob for classification + memory."""
    summary = (event.get("summary") or "(no title)").strip()
    description = (event.get("description") or "").strip()
    location = (event.get("location") or "").strip()

    start = _extract_datetime(event.get("start"))
    end = _extract_datetime(event.get("end"))
    timeframe = start or "unknown"
    if end and end != start:
        timeframe = f"{start} → {end}"

    attendees = event.get("attendees") or []
    attendee_lines = [
        a.get("email", "") + (" (organizer)" if a.get("organizer") else "")
        for a in attendees
        if a.get("email")
    ]

    parts: List[str] = [f"# {summary}", f"When: {timeframe}"]
    if location:
        parts.append(f"Where: {location}")
    if attendee_lines:
        parts.append("Attendees: " + ", ".join(attendee_lines[:15]))
    if description:
        parts.append("")
        parts.append(description[:2000])
    return "\n".join(parts)


def _extract_datetime(obj: Optional[Dict[str, Any]]) -> Optional[str]:
    if not obj:
        return None
    return obj.get("dateTime") or obj.get("date")


# ---------------------------------------------------------------------------
# Google Calendar client
# ---------------------------------------------------------------------------

def _build_service(access_token: str):
    """Construct a Calendar v3 client from a bearer access token."""
    creds = Credentials(token=access_token)
    # cache_discovery=False silences the oauth2client cache warning and
    # avoids an unnecessary on-disk write inside the container.
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _fetch_events(access_token: str) -> List[Dict[str, Any]]:
    """Pull events within [-7d, +14d] from primary. Expands recurrences."""
    service = _build_service(access_token)
    time_min = (datetime.now(timezone.utc) - timedelta(days=PAST_WINDOW_DAYS)).isoformat()
    time_max = (datetime.now(timezone.utc) + timedelta(days=FUTURE_WINDOW_DAYS)).isoformat()
    resp = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,     # expand recurring events into instances
            orderBy="startTime",
            maxResults=MAX_EVENTS,
        )
        .execute()
    )
    return resp.get("items", [])


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

async def ingest_recent(user_id: uuid.UUID, db: AsyncSession) -> Dict[str, Any]:
    """
    Run one ingest cycle for a user. Returns a summary dict the router can
    return to the UI.

    Shape of the summary:
        {
          "fetched": int,     # events returned by Google
          "created": int,     # memory entries written
          "skipped": int,     # duplicates (already ingested)
          "inbox": int,       # routed to Inbox due to low confidence / error
          "by_project": {project_id: count},
        }
    """
    access_token = await google_oauth_service.load_valid_token_for_user(user_id, db)
    if access_token is None:
        raise RuntimeError(
            "Google is not connected (or token refresh failed). Reconnect in Settings."
        )

    try:
        events = _fetch_events(access_token)
    except Exception as exc:
        logger.exception("calendar: fetch failed for user %s", user_id)
        raise RuntimeError(f"Google Calendar fetch failed: {exc}") from exc

    summary = {
        "fetched": len(events),
        "created": 0,
        "skipped": 0,
        "inbox": 0,
        "by_project": {},
    }

    # Pre-query existing source_refs so we skip duplicates in one roundtrip
    # rather than SELECT-per-event.
    source_refs = [SOURCE_PREFIX + e["id"] for e in events if e.get("id")]
    already_ingested: set = set()
    if source_refs:
        existing_rows = await db.execute(
            select(MemoryEntry.source_ref).where(
                MemoryEntry.source_ref.in_(source_refs)
            )
        )
        already_ingested = {r[0] for r in existing_rows.fetchall()}

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue
        source_ref = SOURCE_PREFIX + event_id
        if source_ref in already_ingested:
            summary["skipped"] += 1
            continue

        content = _format_event_text(event)

        try:
            classification = await classifier_service.classify_into_project(
                content=content,
                user_id=user_id,
                db=db,
            )
        except Exception as exc:
            # classifier has its own fallbacks, but just in case
            logger.warning("calendar: classification crashed for %s: %s", event_id, exc)
            continue

        # Store as a memory entry — we intentionally bypass the
        # memory_service.add_entry path (which emits its own
        # "memory.added" event) so the feed sees one clean "ingest.calendar"
        # per event instead of two rows per event.
        entry = MemoryEntry(
            project_id=classification.project_id,
            entry_type=CALENDAR_ENTRY_TYPE,
            content=content,
            source_ref=source_ref,
        )
        db.add(entry)
        await db.flush()

        await log_event(
            db,
            classification.project_id,
            "ingest.calendar",
            f"Calendar event: {(event.get('summary') or '(no title)')[:120]}",
            user_id=user_id,
            source="ingest",
            details={
                "memory_entry_id": str(entry.id),
                "google_event_id": event_id,
                "classifier_confidence": round(classification.confidence, 2),
                "classifier_reason": classification.reason,
                "inbox_fallback": classification.fallback_to_inbox,
            },
        )

        summary["created"] += 1
        if classification.fallback_to_inbox:
            summary["inbox"] += 1
        key = str(classification.project_id)
        summary["by_project"][key] = summary["by_project"].get(key, 0) + 1

    return summary
