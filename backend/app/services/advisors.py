"""Advisor roster — reads from domain config.

Backwards-compat: keeps the same public symbols other services already
call (ADVISOR_REGISTRY, get_advisor, get_all_advisors, get_advisor_info_list,
route_to_advisors, AdvisorConfig) so consumers don't need to change.

The LLM-based router is preserved but now validates candidate IDs against
the live persona pool rather than the old hardcoded dict.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from app.schemas.domain_config import Persona
from app.services.domain_config import get_loader

logger = logging.getLogger(__name__)

# Compat alias — old code may import "AdvisorConfig" or use isinstance checks.
AdvisorConfig = Persona

# Default fallback when router fails — must match IDs in cofounder.yaml.
DEFAULT_ADVISORS = ["yc_partner", "alex_hormozi", "dan_koe"]


# ---------------------------------------------------------------------------
# Registry shim — exposes a dict-like object backed by the live persona pool.
# chat_service does: `advisor_id in ADVISOR_REGISTRY` and dict lookups.
# ---------------------------------------------------------------------------

class _AdvisorRegistry:
    """Thin dict shim that delegates to the live persona pool."""

    def __contains__(self, advisor_id: str) -> bool:
        try:
            pool = get_loader().get_personas("cofounder")
        except Exception:
            return False
        return any(p.id == advisor_id for p in pool.personas)

    def get(self, advisor_id: str, default: Optional[Persona] = None) -> Optional[Persona]:
        try:
            pool = get_loader().get_personas("cofounder")
        except Exception:
            return default
        for p in pool.personas:
            if p.id == advisor_id:
                return p
        return default

    def values(self) -> List[Persona]:
        try:
            return get_loader().get_personas("cofounder").personas
        except Exception:
            return []

    def keys(self) -> List[str]:
        return [p.id for p in self.values()]

    def items(self):  # type: ignore[override]
        return [(p.id, p) for p in self.values()]

    def __getitem__(self, advisor_id: str) -> Persona:
        p = self.get(advisor_id)
        if p is None:
            raise KeyError(advisor_id)
        return p


ADVISOR_REGISTRY = _AdvisorRegistry()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_advisor(advisor_id: str) -> Optional[Persona]:
    """Return a single advisor config by ID, or None if not found."""
    return ADVISOR_REGISTRY.get(advisor_id)


def get_all_advisors() -> List[Persona]:
    """Return all advisor configs in pool order."""
    return ADVISOR_REGISTRY.values()


def get_advisor_info_list() -> List[Dict[str, Any]]:
    """Return advisor metadata dicts without system prompts (for API responses)."""
    return [
        {
            "id": p.id,
            "name": p.name,
            "tagline": p.tagline,
            "expertise": p.expertise,
            "color": p.color,
            "avatar": p.avatar,
        }
        for p in ADVISOR_REGISTRY.values()
    ]


def get_advisor_count() -> int:
    """Return the number of advisors in the pool."""
    return len(ADVISOR_REGISTRY.values())


# ---------------------------------------------------------------------------
# Router agent — selects 3-4 advisors per question using cloud AI.
#
# The LLM router is preserved to avoid losing functionality. The advisor list
# it receives and validates against is now sourced from the persona pool,
# not the old hardcoded dict.
# ---------------------------------------------------------------------------

_ROUTER_SYSTEM = """\
You are a routing agent for a Co-Founder Roundtable. Given a user's question, you must select \
the 3-4 most relevant advisors from the following list.

ADVISORS:
{advisor_list}

RULES:
- Always include yc_partner if the question is about startup strategy, fundraising, or PMF
- Pick 3-4 advisors whose expertise is MOST relevant to the specific question
- Return ONLY a JSON array of advisor IDs, e.g. ["yc_partner", "alex_hormozi", "dan_koe"]
- No explanation, no markdown, no other text — just the JSON array
"""


def _build_router_prompt() -> str:
    """Build the router system prompt with the current advisor list from config."""
    lines = []
    for p in ADVISOR_REGISTRY.values():
        tags = ", ".join(p.expertise)
        lines.append(f"- {p.id}: {p.name} — {p.tagline} (expertise: {tags})")
    advisor_list = "\n".join(lines)
    return _ROUTER_SYSTEM.format(advisor_list=advisor_list)


async def route_to_advisors(user_message: str) -> List[str]:
    """Call cloud AI to pick 3-4 relevant advisors for the given question.

    Returns a list of advisor IDs. Falls back to DEFAULT_ADVISORS on any failure.
    IDs are validated against the live persona pool (not a hardcoded dict).
    """
    from app.services.ai_client import get_cloud_client  # local import avoids circular

    try:
        client = get_cloud_client()
        system_prompt = _build_router_prompt()
        raw = await client.complete(system_prompt, user_message)

        # Strip markdown fences if the model wraps in ```json ... ```
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        advisor_ids = json.loads(cleaned)

        # Validate: must be a list of known advisor IDs
        if not isinstance(advisor_ids, list):
            logger.warning("Router returned non-list: %s", type(advisor_ids))
            return list(DEFAULT_ADVISORS)

        valid_ids = [aid for aid in advisor_ids if aid in ADVISOR_REGISTRY]
        if len(valid_ids) < 2:
            logger.warning("Router returned too few valid advisors: %s", valid_ids)
            return list(DEFAULT_ADVISORS)

        return valid_ids[:4]  # Cap at 4

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Router JSON parse failed: %s", exc)
        return list(DEFAULT_ADVISORS)
    except Exception as exc:
        logger.error("Router agent failed: %s", exc, exc_info=True)
        return list(DEFAULT_ADVISORS)
