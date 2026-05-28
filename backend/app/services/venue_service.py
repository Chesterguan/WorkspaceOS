"""
Venue service: resolve submission guidelines for academic venues.

Resolution order for resolve_venue():
  1. Cache (VenueCache table) — newest match wins
  2. Known-venue dict / web lookup — built-in defaults for major conferences
  3. AI inference — cloud model infers likely constraints from venue name
  4. Manual fallback — empty guidelines with source="manual"

Results from steps 2 and 3 are persisted to VenueCache so subsequent calls
skip the expensive lookup.
"""
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.venue import VenueCache
from app.services.agents import extract_json
from app.services.ai_client import get_cloud_client
from app.services.egress_recorder import EgressRecorder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VenueGuidelines — structured representation of submission constraints
# ---------------------------------------------------------------------------

@dataclass
class VenueGuidelines:
    """Structured submission guidelines for an academic venue."""

    venue_name: str
    page_limit: Optional[int] = None
    word_limit: Optional[int] = None
    template: Optional[str] = None
    anonymization: bool = False
    deadline: Optional[str] = None
    topics: List[str] = field(default_factory=list)
    source: str = "manual"
    venue_url: Optional[str] = None

    def to_dict(self) -> Dict:
        """Return a plain dict representation (compatible with JSON serialisation)."""
        return asdict(self)

    def has_constraints(self) -> bool:
        """True when at least one hard submission constraint (page or word limit) is set."""
        return self.page_limit is not None or self.word_limit is not None


# ---------------------------------------------------------------------------
# _KNOWN_VENUES — built-in defaults for major ML/AI/NLP/CV conferences
# ---------------------------------------------------------------------------

# Keys are lowercase canonical names. Values are kwargs for VenueGuidelines
# (venue_name is added dynamically by _match_known_venue).
_KNOWN_VENUES: Dict[str, Dict] = {
    "icml": {
        "page_limit": 8,
        "template": "icml",
        "anonymization": True,
    },
    "neurips": {
        "page_limit": 9,
        "template": "neurips",
        "anonymization": True,
    },
    "iclr": {
        "page_limit": 10,
        "template": "iclr",
        "anonymization": True,
    },
    "aaai": {
        "page_limit": 7,
        "template": "aaai",
        "anonymization": True,
    },
    "cvpr": {
        "page_limit": 8,
        "template": "cvpr",
        "anonymization": True,
    },
    "acl": {
        "page_limit": 8,
        "template": "acl",
        "anonymization": True,
    },
    "emnlp": {
        "page_limit": 8,
        "template": "acl",
        "anonymization": True,
    },
    "naacl": {
        "page_limit": 8,
        "template": "acl",
        "anonymization": True,
    },
    "eccv": {
        "page_limit": 14,
        "template": "eccv",
        "anonymization": True,
    },
    "sigchi": {
        "page_limit": 10,
        "template": "acm-sigconf",
        "anonymization": True,
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _match_known_venue(venue_name: str) -> Optional[Dict]:
    """Return the known-venue dict entry for venue_name via case-insensitive substring match.

    Checks whether any key in _KNOWN_VENUES appears as a substring of the
    normalised venue_name (e.g. "NeurIPS 2026" matches "neurips").
    Returns None if no match is found.
    """
    normalised = venue_name.lower()
    for key, defaults in _KNOWN_VENUES.items():
        if key in normalised:
            return defaults
    return None


async def _lookup_cache(venue_name: str, db: AsyncSession) -> Optional[VenueGuidelines]:
    """Query VenueCache for an existing entry matching venue_name.

    Matches case-insensitively and returns the most recently fetched entry.
    Returns None if no match exists.
    """
    # ilike gives case-insensitive equality; use % wildcards for substring match
    # so "ICML 2026" finds a cached entry stored as "icml".
    # Escape SQL LIKE wildcards in user input to prevent unintended matching.
    normalised = venue_name.lower().replace("%", "\\%").replace("_", "\\_")
    result = await db.execute(
        select(VenueCache)
        .where(VenueCache.venue_name.ilike(f"%{normalised}%"))
        .order_by(VenueCache.fetched_at.desc())
    )
    row: Optional[VenueCache] = result.scalar_one_or_none()
    if row is None:
        return None

    return VenueGuidelines(
        venue_name=row.venue_name,
        page_limit=row.page_limit,
        word_limit=row.word_limit,
        template=row.template,
        anonymization=row.anonymization,
        deadline=row.deadline,
        topics=list(row.topics) if row.topics else [],
        source="cached",
        venue_url=row.venue_url,
    )


def _fetch_web(venue_name: str) -> Optional[VenueGuidelines]:
    """Attempt to resolve venue guidelines from the web.

    For now, known-venue matching IS the web fetch — actual HTTP scraping is
    future work. Returns a VenueGuidelines with source="web" on a match.
    """
    defaults = _match_known_venue(venue_name)
    if defaults is None:
        return None

    return VenueGuidelines(
        venue_name=venue_name,
        source="web",
        **defaults,
    )


async def _infer_with_ai(venue_name: str) -> Optional[VenueGuidelines]:
    """Ask the cloud AI to infer submission guidelines for the given venue.

    Returns a VenueGuidelines with source="ai_inferred", or None on any failure
    (network error, bad JSON, etc.).
    """
    system_prompt = (
        "You are an expert on academic publishing venues. "
        "Given a venue name, infer its typical submission guidelines. "
        "Respond ONLY with a JSON object — no prose, no markdown fences. "
        "Required keys: page_limit (int or null), word_limit (int or null), "
        "template (string or null, e.g. 'ieee', 'acm-sigconf', 'neurips'), "
        "anonymization (bool), deadline (string or null), topics (list of strings), "
        "venue_url (string or null)."
    )
    user_prompt = (
        f"Venue: {venue_name}\n\n"
        "Return the JSON object with the keys described above. "
        "Use null for any field you cannot determine with confidence."
    )

    try:
        client = get_cloud_client()
        async with EgressRecorder(
            surface="publish",
            service="venue_service.suggest",
            provider=type(client).__name__.lower().replace("client", ""),
            model=getattr(client, "_model", None) or getattr(client, "chat_model", None),
            user_id=None,
            project_id=None,
        ) as rec:
            rec.field("system_prompt", system_prompt)
            rec.field("project_profile", user_prompt)
            raw = await client.complete(system_prompt, user_prompt)
        data = extract_json(raw)
        if not data:
            return None

        return VenueGuidelines(
            venue_name=venue_name,
            page_limit=data.get("page_limit"),
            word_limit=data.get("word_limit"),
            template=data.get("template"),
            anonymization=bool(data.get("anonymization", False)),
            deadline=data.get("deadline"),
            topics=list(data.get("topics") or []),
            source="ai_inferred",
            venue_url=data.get("venue_url"),
        )
    except Exception:
        logger.exception("_infer_with_ai: failed for venue '%s'", venue_name)
        return None


async def _save_to_cache(guidelines: VenueGuidelines, db: AsyncSession) -> None:
    """Persist a VenueGuidelines object to the VenueCache table."""
    row = VenueCache(
        venue_name=guidelines.venue_name,
        venue_url=guidelines.venue_url,
        page_limit=guidelines.page_limit,
        word_limit=guidelines.word_limit,
        template=guidelines.template,
        anonymization=guidelines.anonymization,
        deadline=guidelines.deadline,
        topics=guidelines.topics if guidelines.topics else None,
        source=guidelines.source,
    )
    db.add(row)
    await db.flush()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def resolve_venue(venue_name: str, db: AsyncSession) -> VenueGuidelines:
    """Resolve submission guidelines for a venue by name.

    Resolution order:
      1. VenueCache table — fastest, no external calls
      2. Built-in known-venue dict (treated as a web source)
      3. Cloud AI inference
      4. Manual fallback — returns empty guidelines, never raises

    Results from steps 2 and 3 are saved to the cache so subsequent calls
    are served from step 1.
    """
    # Step 1 — cache hit
    cached = await _lookup_cache(venue_name, db)
    if cached is not None:
        logger.debug("resolve_venue: cache hit for '%s'", venue_name)
        return cached

    # Step 2 — known venue / web
    web_result = _fetch_web(venue_name)
    if web_result is not None:
        logger.debug("resolve_venue: known-venue match for '%s'", venue_name)
        await _save_to_cache(web_result, db)
        return web_result

    # Step 3 — AI inference
    ai_result = await _infer_with_ai(venue_name)
    if ai_result is not None:
        logger.debug("resolve_venue: AI-inferred guidelines for '%s'", venue_name)
        await _save_to_cache(ai_result, db)
        return ai_result

    # Step 4 — manual fallback
    logger.warning("resolve_venue: no guidelines found for '%s'; returning empty fallback", venue_name)
    return VenueGuidelines(venue_name=venue_name, source="manual")
