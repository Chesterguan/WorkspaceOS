"""
Outlook Mail ingest via Microsoft Graph.

Window: last N_DAYS of Inbox (default 3). Per-run cap MAX_MESSAGES.
Dedupe: source_ref = f"outlook-mail:{id}".

Deliberately ingests bodyPreview (plaintext summary Graph generates for us)
rather than the full HTML body. Reasons:
  1. bodyPreview is ~250 chars — enough for classification, well-bounded
     for embeddings, avoids dragging marketing email layout into memory.
  2. Full bodies often contain long signatures, quoted threads, and
     HTML that balloons the prompt without improving signal.
If we later need full bodies for specific items the user pins, we can
re-fetch on demand; that's a v2 concern.
"""
import logging
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

MAIL_ENTRY_TYPE = "email"
SOURCE_PREFIX = "outlook-mail:"

N_DAYS = 3
MAX_MESSAGES = 50

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _addrs(recipients: List[Dict[str, Any]]) -> List[str]:
    """Extract plain 'name <addr>' strings from Graph's recipients list."""
    out: List[str] = []
    for r in recipients or []:
        email_obj = r.get("emailAddress") or {}
        name = email_obj.get("name") or ""
        addr = email_obj.get("address") or ""
        if name and addr and name != addr:
            out.append(f"{name} <{addr}>")
        elif addr:
            out.append(addr)
    return out


def _format_mail_text(msg: Dict[str, Any]) -> str:
    """Compact text blob for classification + memory."""
    subject = (msg.get("subject") or "(no subject)").strip()
    received = msg.get("receivedDateTime") or ""
    sender = ""
    if msg.get("from"):
        sender_obj = (msg["from"] or {}).get("emailAddress") or {}
        s_name = sender_obj.get("name", "")
        s_addr = sender_obj.get("address", "")
        sender = f"{s_name} <{s_addr}>" if s_name and s_addr else (s_addr or s_name)
    to = _addrs(msg.get("toRecipients") or [])[:10]
    cc = _addrs(msg.get("ccRecipients") or [])[:5]
    preview = (msg.get("bodyPreview") or "").strip()

    parts: List[str] = [f"# {subject}"]
    if sender:
        parts.append(f"From: {sender}")
    if to:
        parts.append("To: " + ", ".join(to))
    if cc:
        parts.append("Cc: " + ", ".join(cc))
    if received:
        parts.append(f"Received: {received}")
    if preview:
        parts.append("")
        parts.append(preview[:1500])
    return "\n".join(parts)


async def _fetch_messages(access_token: str) -> List[Dict[str, Any]]:
    """Graph /me/messages — recent Inbox items, newest first."""
    since = (datetime.now(timezone.utc) - timedelta(days=N_DAYS)).isoformat()
    url = f"{_GRAPH_BASE}/me/messages"
    params = {
        "$top": str(MAX_MESSAGES),
        "$orderby": "receivedDateTime desc",
        "$filter": f"receivedDateTime ge {since}",
        "$select": (
            "id,subject,from,toRecipients,ccRecipients,"
            "receivedDateTime,bodyPreview,isDraft"
        ),
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        # Graph normally returns bodies as HTML; we only want preview text
        # so don't need to tweak Prefer for body type.
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code == 401:
            raise RuntimeError(
                "Microsoft token rejected (401). Reconnect Microsoft in Settings."
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Graph /me/messages failed ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json().get("value", [])


async def ingest_recent(user_id: uuid.UUID, db: AsyncSession) -> Dict[str, Any]:
    """Fetch recent messages, classify, store. Same summary shape as the
    calendar services so the UI can share result-handling code."""
    access_token = await microsoft_oauth_service.load_valid_token_for_user(user_id, db)
    if access_token is None:
        raise RuntimeError(
            "Microsoft is not connected (or token refresh failed). "
            "Reconnect in Settings."
        )

    try:
        messages = await _fetch_messages(access_token)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.exception("outlook mail: fetch failed for user %s", user_id)
        raise RuntimeError(f"Outlook mail fetch failed: {exc}") from exc

    # Drop drafts — we care about received conversations, not stuff the
    # user has partially composed. Cheaper to filter here than paginate
    # Graph with a filter it often struggles to combine with $top.
    messages = [m for m in messages if not m.get("isDraft")]

    summary = {
        "fetched": len(messages),
        "created": 0,
        "skipped": 0,
        "inbox": 0,
        "by_project": {},
    }

    source_refs = [SOURCE_PREFIX + m["id"] for m in messages if m.get("id")]
    already: set = set()
    if source_refs:
        rows = await db.execute(
            select(MemoryEntry.source_ref).where(MemoryEntry.source_ref.in_(source_refs))
        )
        already = {r[0] for r in rows.fetchall()}

    for msg in messages:
        msg_id = msg.get("id")
        if not msg_id:
            continue
        source_ref = SOURCE_PREFIX + msg_id
        if source_ref in already:
            summary["skipped"] += 1
            continue

        content = _format_mail_text(msg)

        try:
            classification = await classifier_service.classify_into_project(
                content=content, user_id=user_id, db=db,
            )
        except Exception as exc:
            logger.warning("outlook mail: classification crashed for %s: %s", msg_id, exc)
            continue

        entry = MemoryEntry(
            project_id=classification.project_id,
            entry_type=MAIL_ENTRY_TYPE,
            content=content,
            source_ref=source_ref,
        )
        db.add(entry)
        await db.flush()

        await log_event(
            db,
            classification.project_id,
            "ingest.outlook_mail",
            f"Email: {(msg.get('subject') or '(no subject)')[:120]}",
            user_id=user_id,
            source="ingest",
            details={
                "memory_entry_id": str(entry.id),
                "outlook_message_id": msg_id,
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
