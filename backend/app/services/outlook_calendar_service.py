"""
Outlook Calendar ingest via Microsoft Graph — mirrors
google_calendar_service but against the Graph REST API.

Uses `calendarView` (not `events`) so recurring series are expanded into
individual instances within the window, matching our Google path's
`singleEvents=True` behaviour.

Window: -7d → +14d, primary calendar, capped at MAX_EVENTS per run.
Dedupe: source_ref=f"outlook-cal:{id}".
"""
import html
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.services import classifier_service, microsoft_oauth_service
from app.services.activity_service import log_event

logger = logging.getLogger(__name__)

CALENDAR_ENTRY_TYPE = "calendar_event"
SOURCE_PREFIX = "outlook-cal:"

PAST_WINDOW_DAYS = 7
FUTURE_WINDOW_DAYS = 14
MAX_EVENTS = 100

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Minimal HTML → text — Graph returns event bodies as HTML by default
# and we don't need the markup to classify. A full parser would be
# overkill; a single regex stripping tags is good enough for prompts.
_TAG_RE = re.compile(r"<[^>]+>")


_WS_RE = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    if not s:
        return ""
    # Each tag becomes a single space; then collapse runs of whitespace so
    # "Agenda: <b>Q2</b> review" → "Agenda: Q2 review" rather than double
    # spaces the LLM would see as formatting noise.
    stripped = html.unescape(_TAG_RE.sub(" ", s))
    return _WS_RE.sub(" ", stripped).strip()


def _format_event_text(event: Dict[str, Any]) -> str:
    """Render a Graph event into a compact text blob for classification."""
    subject = (event.get("subject") or "(no title)").strip()
    location = ((event.get("location") or {}).get("displayName") or "").strip()
    start = (event.get("start") or {}).get("dateTime") or ""
    end = (event.get("end") or {}).get("dateTime") or ""
    timeframe = f"{start} → {end}" if end and end != start else (start or "unknown")

    body_raw = (event.get("body") or {}).get("content", "")
    body = _strip_html(body_raw)[:2000]

    attendees = [
        (a.get("emailAddress") or {}).get("address", "")
        for a in event.get("attendees") or []
    ]
    attendees = [a for a in attendees if a][:15]
    organizer = ((event.get("organizer") or {}).get("emailAddress") or {}).get("address", "")

    parts: List[str] = [f"# {subject}", f"When: {timeframe}"]
    if location:
        parts.append(f"Where: {location}")
    if organizer:
        parts.append(f"Organizer: {organizer}")
    if attendees:
        parts.append("Attendees: " + ", ".join(attendees))
    if body:
        parts.append("")
        parts.append(body)
    return "\n".join(parts)


async def _fetch_events(access_token: str) -> List[Dict[str, Any]]:
    """Graph calendarView — expands recurring events within the window."""
    start = (datetime.now(timezone.utc) - timedelta(days=PAST_WINDOW_DAYS)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=FUTURE_WINDOW_DAYS)).isoformat()
    url = f"{_GRAPH_BASE}/me/calendarView"
    params = {
        "startDateTime": start,
        "endDateTime": end,
        "$orderby": "start/dateTime",
        "$top": str(MAX_EVENTS),
        "$select": "id,subject,start,end,location,organizer,attendees,body",
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        # UTC dateTimes back from Graph — avoids per-user tz surprises
        "Prefer": 'outlook.timezone="UTC"',
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code == 401:
            raise RuntimeError(
                "Microsoft token rejected (401). Reconnect Microsoft in Settings."
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Graph calendarView failed ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json().get("value", [])


async def ingest_recent(user_id: uuid.UUID, db: AsyncSession) -> Dict[str, Any]:
    """Run one ingest cycle for a user. Same return shape as the Google
    Calendar service so the frontend can reuse its result handling."""
    access_token = await microsoft_oauth_service.load_valid_token_for_user(user_id, db)
    if access_token is None:
        raise RuntimeError(
            "Microsoft is not connected (or token refresh failed). "
            "Reconnect in Settings."
        )

    try:
        events = await _fetch_events(access_token)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("outlook calendar: fetch failed for user %s", user_id)
        raise RuntimeError(f"Outlook calendar fetch failed: {exc}") from exc

    summary = {
        "fetched": len(events),
        "created": 0,
        "skipped": 0,
        "inbox": 0,
        "by_project": {},
    }

    source_refs = [SOURCE_PREFIX + e["id"] for e in events if e.get("id")]
    already: set = set()
    if source_refs:
        rows = await db.execute(
            select(MemoryEntry.source_ref).where(MemoryEntry.source_ref.in_(source_refs))
        )
        already = {r[0] for r in rows.fetchall()}

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue
        source_ref = SOURCE_PREFIX + event_id
        if source_ref in already:
            summary["skipped"] += 1
            continue

        content = _format_event_text(event)

        try:
            classification = await classifier_service.classify_into_project(
                content=content, user_id=user_id, db=db,
            )
        except Exception as exc:
            logger.warning("outlook calendar: classification crashed for %s: %s", event_id, exc)
            continue

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
            "ingest.outlook_calendar",
            f"Outlook event: {(event.get('subject') or '(no title)')[:120]}",
            user_id=user_id,
            source="ingest",
            details={
                "memory_entry_id": str(entry.id),
                "outlook_event_id": event_id,
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
