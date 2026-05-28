"""
Project classifier — given a piece of ingested content (calendar event,
email, etc.), pick the user's project it most plausibly belongs to.

Design:
  * One cloud-AI call per item; input is the content blob + a compact
    catalogue of the user's projects (name + description + short wiki
    excerpt). Output is strict JSON {project_id, confidence, reason}.
  * Below the confidence threshold we return the user's Inbox project so
    nothing ever falls on the floor. The caller decides what to do with
    the low-confidence bucket; the classifier's job is just "best guess".
  * Context window: we cap the per-project slice so a user with 20+
    projects doesn't blow the prompt budget.

This is deliberately a thin wrapper — no retries, no caching, no
streaming. Tune after we see real classification quality in the feed.
"""
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import MemoryEntry
from app.models.project import Project
from app.services import inbox_service
from app.services.ai_client import get_cloud_client
from app.services.egress_recorder import EgressRecorder

logger = logging.getLogger(__name__)

# Below this score we don't trust the pick — fallback to Inbox. Tuneable
# via CLASSIFIER_CONFIDENCE_THRESHOLD if we want to A/B later.
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

# Per-project budget in the catalogue prompt. Keeps the overall prompt
# sane even with 20+ projects.
_WIKI_EXCERPT_CHARS = 400
_DESC_EXCERPT_CHARS = 200


@dataclass
class Classification:
    project_id: uuid.UUID
    confidence: float
    reason: str
    fallback_to_inbox: bool  # True iff we used the Inbox fallback


_SYSTEM_PROMPT = (
    "You classify an ingested item (calendar event, email, note) into one of a "
    "user's projects. Return STRICT JSON: "
    '{"project_id": "<uuid from the catalog>", "confidence": 0.0-1.0, "reason": "<short>"}. '
    "Pick the project whose wiki / description best matches the item's topic, "
    "participants, or explicit references. If nothing fits clearly, still pick "
    "your best guess but return a LOW confidence (<0.5). Never invent a UUID; "
    "use one from the catalog. No prose outside the JSON."
)


async def _build_project_catalogue(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> List[dict]:
    """Compact project list for the prompt: id, name, description, wiki excerpt."""
    rows = await db.execute(
        select(Project.id, Project.name, Project.description, Project.slug)
        .where(Project.user_id == user_id)
        .order_by(Project.created_at.asc())
    )
    projects = [dict(r._mapping) for r in rows.fetchall()]

    # Grab each project's latest wiki_summary in one query
    ids = [p["id"] for p in projects]
    wikis: dict = {}
    if ids:
        wiki_rows = await db.execute(
            select(MemoryEntry.project_id, MemoryEntry.content)
            .where(
                MemoryEntry.project_id.in_(ids),
                MemoryEntry.entry_type == "wiki_summary",
            )
        )
        for pid, content in wiki_rows.fetchall():
            wikis[pid] = content

    catalogue: List[dict] = []
    for p in projects:
        wiki = (wikis.get(p["id"]) or "").strip()
        desc = (p["description"] or "").strip()
        catalogue.append({
            "project_id": str(p["id"]),
            "name": p["name"],
            "slug": p["slug"],
            "description": desc[:_DESC_EXCERPT_CHARS],
            "wiki_excerpt": wiki[:_WIKI_EXCERPT_CHARS],
        })
    return catalogue


def _extract_json(text: str) -> Optional[dict]:
    """Tolerate AI responses wrapped in code fences / trailing prose."""
    # Strip ```json ... ``` fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    # Fallback: slice between the first { and the last }
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None


async def build_catalogue_for_user(
    user_id: uuid.UUID, db: AsyncSession,
) -> List[dict]:
    """Public wrapper around the internal catalogue builder. Callers that
    classify many items in a row (ingest loops) should build once and pass
    it in via `catalogue=` to avoid N duplicate `projects` + `wiki_summary`
    queries per batch."""
    return await _build_project_catalogue(user_id, db)


async def classify_into_project(
    content: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    catalogue: Optional[List[dict]] = None,
) -> Classification:
    """
    Classify `content` into one of user_id's projects. Returns a
    Classification. On low confidence OR AI failure, returns an Inbox
    fallback so the caller can always count on a valid project_id.

    Pass `catalogue=` to skip the per-call DB rebuild — use this when
    classifying many items in a row.
    """
    if catalogue is None:
        catalogue = await _build_project_catalogue(user_id, db)

    # No projects (new user): everything goes to Inbox.
    if not catalogue:
        inbox = await inbox_service.get_or_create_inbox(user_id, db)
        return Classification(
            project_id=inbox.id,
            confidence=0.0,
            reason="User has no projects yet; ingested to Inbox.",
            fallback_to_inbox=True,
        )

    user_prompt = (
        "CATALOG:\n"
        + json.dumps(catalogue, indent=2)
        + "\n\nITEM TO CLASSIFY:\n"
        + content[:4000]
    )

    # One cloud call. No retries — classifier failures are rare and the
    # Inbox fallback is the right behaviour when they happen.
    ai = get_cloud_client()
    try:
        async with EgressRecorder(
            surface="inbox",
            service="classifier_service.classify",
            provider=type(ai).__name__.lower().replace("client", ""),
            model=getattr(ai, "_model", None) or getattr(ai, "chat_model", None),
            user_id=user_id,
            project_id=None,
        ) as rec:
            rec.field("system_prompt", _SYSTEM_PROMPT)
            rec.field("project_catalogue", json.dumps(catalogue, indent=2))
            rec.field("item_content", content[:4000])
            raw = await ai.complete(system=_SYSTEM_PROMPT, user=user_prompt)
    except Exception as exc:
        logger.warning("classifier: AI call failed: %s", exc)
        inbox = await inbox_service.get_or_create_inbox(user_id, db)
        return Classification(
            project_id=inbox.id,
            confidence=0.0,
            reason=f"Classifier error: {exc}",
            fallback_to_inbox=True,
        )

    parsed = _extract_json(raw)
    if not parsed:
        logger.warning("classifier: unparseable response: %s", raw[:200])
        inbox = await inbox_service.get_or_create_inbox(user_id, db)
        return Classification(
            project_id=inbox.id,
            confidence=0.0,
            reason="Classifier returned unparseable JSON.",
            fallback_to_inbox=True,
        )

    try:
        picked_id = uuid.UUID(str(parsed.get("project_id", "")))
    except (ValueError, TypeError):
        inbox = await inbox_service.get_or_create_inbox(user_id, db)
        return Classification(
            project_id=inbox.id,
            confidence=0.0,
            reason="Classifier returned an invalid project_id.",
            fallback_to_inbox=True,
        )

    # Guard: the AI sometimes hallucinates IDs. Reject anything not in the
    # user's actual project list.
    valid_ids = {uuid.UUID(p["project_id"]) for p in catalogue}
    if picked_id not in valid_ids:
        inbox = await inbox_service.get_or_create_inbox(user_id, db)
        return Classification(
            project_id=inbox.id,
            confidence=0.0,
            reason="Classifier picked a project_id that doesn't belong to the user.",
            fallback_to_inbox=True,
        )

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(parsed.get("reason", ""))[:300]

    if confidence < threshold:
        inbox = await inbox_service.get_or_create_inbox(user_id, db)
        return Classification(
            project_id=inbox.id,
            confidence=confidence,
            reason=f"Low confidence ({confidence:.2f}): {reason}",
            fallback_to_inbox=True,
        )

    return Classification(
        project_id=picked_id,
        confidence=confidence,
        reason=reason,
        fallback_to_inbox=False,
    )
