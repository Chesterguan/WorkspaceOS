"""
Local-ingest service — accepts pre-authenticated items from a host-side
bridge (the macOS Outlook AppleScript script today; arbitrary local tools
tomorrow) and runs them through the same classifier / memory / activity
pipeline as the cloud skills.

The bridge already has the user's authorisation by virtue of running in
the user's login session on their Mac — we don't need OAuth or Graph or
Microsoft at all. This service just does the last mile: format item
content into a text blob, classify, store, emit feed event.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.schemas.local_ingest import LocalIngestItem
from app.services import classifier_service
from app.services.activity_service import log_event

logger = logging.getLogger(__name__)

SOURCE_PREFIX = "mac-outlook:"  # kind is appended: "mac-outlook:calendar:<id>"

# Memory entry_type per kind — keeps parity with the cloud equivalents so
# search / wiki / worklog see a uniform catalogue.
_ENTRY_TYPE_BY_KIND = {
    "calendar": "calendar_event",
    "mail": "email",
}

_EVENT_TYPE_BY_KIND = {
    "calendar": "ingest.mac_outlook",
    "mail": "ingest.mac_outlook",
}


# ---------------------------------------------------------------------------
# Text rendering — one layout per `kind`
# ---------------------------------------------------------------------------

def _render_calendar(item: LocalIngestItem) -> str:
    parts: List[str] = [f"# {item.subject or '(no title)'}"]
    if item.start:
        timeframe = item.start
        if item.end and item.end != item.start:
            timeframe = f"{item.start} → {item.end}"
        parts.append(f"When: {timeframe}")
    if item.location:
        parts.append(f"Where: {item.location}")
    if item.organizer:
        parts.append(f"Organizer: {item.organizer}")
    if item.attendees:
        parts.append("Attendees: " + ", ".join(item.attendees[:15]))
    if item.body:
        parts.append("")
        parts.append(item.body[:2000])
    return "\n".join(parts)


def _render_mail(item: LocalIngestItem) -> str:
    parts: List[str] = [f"# {item.subject or '(no subject)'}"]
    if item.sender:
        parts.append(f"From: {item.sender}")
    if item.to:
        parts.append("To: " + ", ".join(item.to[:10]))
    if item.cc:
        parts.append("Cc: " + ", ".join(item.cc[:5]))
    if item.received_at:
        parts.append(f"Received: {item.received_at}")
    if item.body:
        parts.append("")
        parts.append(item.body[:1500])
    return "\n".join(parts)


def _render_item(item: LocalIngestItem) -> str:
    if item.kind == "calendar":
        return _render_calendar(item)
    if item.kind == "mail":
        return _render_mail(item)
    # Unknown kind — render as-is so nothing is silently dropped; the
    # classifier will still attempt its best guess.
    return (item.subject or "").strip() + "\n\n" + (item.body or "").strip()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def ingest_items(
    user_id: uuid.UUID,
    items: List[LocalIngestItem],
    db: AsyncSession,
) -> Dict[str, Any]:
    """Run each item through the classifier → memory → feed pipeline.

    Same return shape as the Google/Outlook cloud skills so the UI can
    reuse its result-toast component.
    """
    summary: Dict[str, Any] = {
        "fetched": len(items),
        "created": 0,
        "skipped": 0,
        "inbox": 0,
        "by_project": {},
    }
    if not items:
        return summary

    # Build the full set of source_refs up front so we can dedupe in one
    # query instead of N.
    source_refs = [
        f"{SOURCE_PREFIX}{it.kind}:{it.external_id}" for it in items if it.external_id
    ]
    already: set = set()
    if source_refs:
        rows = await db.execute(
            select(MemoryEntry.source_ref).where(MemoryEntry.source_ref.in_(source_refs))
        )
        already = {r[0] for r in rows.fetchall()}

    for item in items:
        if not item.external_id:
            continue
        source_ref = f"{SOURCE_PREFIX}{item.kind}:{item.external_id}"
        if source_ref in already:
            summary["skipped"] += 1
            continue

        content = _render_item(item)
        try:
            classification = await classifier_service.classify_into_project(
                content=content, user_id=user_id, db=db,
            )
        except Exception as exc:
            logger.warning(
                "local-ingest: classification crashed for %s: %s",
                source_ref, exc,
            )
            continue

        entry_type = _ENTRY_TYPE_BY_KIND.get(item.kind, item.kind)
        entry = MemoryEntry(
            project_id=classification.project_id,
            entry_type=entry_type,
            content=content,
            source_ref=source_ref,
        )
        db.add(entry)
        await db.flush()

        summary_line = _summary_line(item)
        await log_event(
            db,
            classification.project_id,
            _EVENT_TYPE_BY_KIND.get(item.kind, "ingest.mac_outlook"),
            summary_line,
            user_id=user_id,
            source="ingest",
            details={
                "memory_entry_id": str(entry.id),
                "kind": item.kind,
                "external_id": item.external_id,
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


def _summary_line(item: LocalIngestItem) -> str:
    """One-line human-readable label for the activity feed."""
    label = item.subject or "(untitled)"
    if item.kind == "calendar":
        return f"Outlook event (Mac): {label[:100]}"
    if item.kind == "mail":
        return f"Email (Mac): {label[:100]}"
    return f"Local {item.kind}: {label[:100]}"
