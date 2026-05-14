"""Publication grounding for research personas.

When a research persona declares `grounding: { source: semantic_scholar,
query: "Drew Endy", max_papers: 5 }`, we want their LLM replies to
anchor against real recent publications rather than hallucinate.

Cheap implementation:
  1. Look up `query` via the existing scholar_service (Semantic Scholar
     + OpenAlex fallback).
  2. Cache the result in-process for 24h — these don't change fast and
     we don't want a Semantic Scholar call per chat turn.
  3. Format the top N as a short bulletted prompt fragment.
  4. Caller prepends it to the persona's system_prompt before sending
     to the LLM.

When the lookup fails (rate limit, network, no matches), we return an
empty string — the persona reverts to ungrounded behavior. Graceful
degrade is the explicit goal here; grounding is an enhancement, not a
hard dependency.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

from app.schemas.domain_config import PersonaGrounding
from app.services import scholar_service

logger = logging.getLogger(__name__)

# (query, source) → (fetched_at_epoch_seconds, formatted_prompt_fragment)
_CACHE: Dict[Tuple[str, str], Tuple[float, str]] = {}
_CACHE_TTL_SECONDS = 24 * 60 * 60


async def grounding_prompt_fragment(grounding: PersonaGrounding) -> str:
    """Return a short fragment listing the persona's recent papers, or
    empty string when grounding can't be resolved.

    Caller pattern (in chat_service.py / research_service.py):

        fragment = await grounding_prompt_fragment(persona.grounding)
        system = (persona.system_prompt + "\\n\\n" + fragment).strip()
    """
    key = (grounding.query.strip(), grounding.source)
    if not key[0]:
        return ""

    now = time.time()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    fragment = ""
    try:
        if grounding.source == "semantic_scholar":
            papers = await scholar_service.search_papers(
                query=grounding.query,
                limit=grounding.max_papers,
            )
            fragment = _format_papers(grounding.query, papers or [])
        else:
            # Future sources: orcid, openalex, custom. v0.2.2 ships
            # semantic_scholar only — the schema reservation makes
            # future sources additive.
            logger.debug("persona_grounding: unsupported source %s", grounding.source)
    except Exception as exc:
        logger.warning("persona_grounding: lookup failed for %r — %s",
                       grounding.query, exc)

    _CACHE[key] = (now, fragment)
    return fragment


def _format_papers(query: str, papers: List[dict]) -> str:
    if not papers:
        return ""
    lines = [
        f"GROUNDING — recent work by {query} (use these as the anchor for "
        f"your factual claims; do not contradict or fabricate beyond them):",
    ]
    for p in papers[:10]:
        title = p.get("title") or "Untitled"
        year = p.get("year") or "n.d."
        venue = p.get("venue") or ""
        venue_str = f" — {venue}" if venue else ""
        lines.append(f"  • {title} ({year}{venue_str})")
    return "\n".join(lines)


def clear_cache() -> None:
    """Test helper / settings hook — flush the in-memory cache."""
    _CACHE.clear()
