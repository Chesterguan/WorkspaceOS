"""Paper Roundtable reviewers — reads from domain config.

Backwards-compat: keeps the same public symbols other services already call
(REVIEWER_REGISTRY, ReviewerConfig, MIN_SCORE_FOR_PASS, MAX_ROUNDTABLE_ROUNDS,
DEFAULT_RESEARCH_REVIEWERS, get_reviewer, get_all_reviewers,
get_reviewer_info_list, run_review_roundtable, build_revision_brief,
route_to_research_reviewers) so consumers don't need to change.

The hardcoded persona prompts and dataclass are gone — reviewer data now comes
from the live "research" persona pool defined in config/.
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import yaml

from app.config import settings
from app.schemas.domain_config import Persona, PersonaPool
from app.services.agents import AgentLog, NamedAgent
from app.services.ai_client import OpenAIClient, get_cloud_client
from app.services.domain_config import get_loader
from app.services.extensions import get_all_extensions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_SCORE_FOR_PASS = 7
MAX_ROUNDTABLE_ROUNDS = 2

# Cross-model diversity: these IDs use OpenAI when configured (Gemini writes,
# OpenAI critiques for genuine cross-model review). Any other reviewer ID
# falls through to the cloud client.
_OPENAI_REVIEWER_IDS = frozenset({"technical_rigor", "novelty_positioning"})

# Compat alias — old call sites may import ReviewerConfig or use it for typing.
ReviewerConfig = Persona


# ---------------------------------------------------------------------------
# Registry shim — exposes a dict-like object backed by the live persona pool.
# ---------------------------------------------------------------------------

class _ReviewerRegistry:
    """Thin dict shim that delegates to the live "research" persona pool."""

    def _pool(self) -> List[Persona]:
        try:
            return list(get_loader().get_personas("research").personas)
        except Exception:
            return []

    def __contains__(self, reviewer_id: str) -> bool:
        return any(p.id == reviewer_id for p in self._pool())

    def __len__(self) -> int:
        return len(self._pool())

    def get(self, reviewer_id: str, default: Optional[Persona] = None) -> Optional[Persona]:
        for p in self._pool():
            if p.id == reviewer_id:
                return p
        return default

    def values(self) -> List[Persona]:
        return self._pool()

    def keys(self) -> List[str]:
        return [p.id for p in self._pool()]

    def items(self):  # type: ignore[override]
        return [(p.id, p) for p in self._pool()]

    def __getitem__(self, reviewer_id: str) -> Persona:
        p = self.get(reviewer_id)
        if p is None:
            raise KeyError(reviewer_id)
        return p


REVIEWER_REGISTRY = _ReviewerRegistry()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_reviewer(reviewer_id: str) -> Optional[Persona]:
    """Return a single reviewer config by ID, or None if not found."""
    return REVIEWER_REGISTRY.get(reviewer_id)


def get_all_reviewers() -> List[Persona]:
    """Return all reviewer configs in pool order."""
    return REVIEWER_REGISTRY.values()


def get_reviewer_info_list() -> List[Dict[str, Any]]:
    """Return reviewer metadata dicts without system prompts (for API responses)."""
    return [
        {
            "id": r.id,
            "name": r.name,
            "modeled_after": r.modeled_after or "",
            "focus": r.focus or "",
            "color": r.color,
            "avatar": r.avatar or "",
        }
        for r in REVIEWER_REGISTRY.values()
    ]


# ---------------------------------------------------------------------------
# Parallel roundtable dispatch
# ---------------------------------------------------------------------------


def _safe_score(value: Any) -> int:
    """Safely convert an AI-returned score to int. Returns 0 on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


async def _run_single_reviewer(
    reviewer: Persona,
    agent: NamedAgent,
    paper_content: str,
    venue_text: str,
    agent_log: AgentLog,
) -> Dict:
    """Run one reviewer and return a structured result dict."""
    user_prompt = f"PAPER TO REVIEW:\n\n{paper_content}"
    if venue_text:
        user_prompt += f"\n\nTARGET VENUE GUIDELINES:\n{venue_text}"

    try:
        result = await agent.complete_json(
            system=reviewer.system_prompt,
            user=user_prompt,
            action="roundtable_review",
            section=reviewer.id,
        )
    except Exception as exc:
        logger.error("Reviewer %s failed: %s", reviewer.id, exc, exc_info=True)
        result = {}

    score = _safe_score(result.get("score", 0))
    agent_log.add(
        agent=f"reviewer_{reviewer.id}",
        action="score",
        detail=f"{reviewer.name} ({reviewer.modeled_after or ''}): {score}/10",
        score=score,
    )

    return {
        "reviewer_id": reviewer.id,
        "reviewer_name": reviewer.name,
        "modeled_after": reviewer.modeled_after or "",
        "focus": reviewer.focus or "",
        "avatar": reviewer.avatar or "",
        "color": reviewer.color,
        "score": score,
        "strengths": result.get("strengths", []),
        "weaknesses": result.get("weaknesses", []),
        "suggestions": result.get("suggestions", []),
        "critical_issues": result.get("critical_issues", []),
    }


async def run_review_roundtable(
    paper_content: str,
    venue_text: str = "",
    agent_log: Optional[AgentLog] = None,
) -> List[Dict]:
    """Dispatch all reviewers in parallel and collect structured feedback.

    For reviewers in _OPENAI_REVIEWER_IDS, prefers OpenAI when configured
    (cross-model diversity against the Gemini writer). Falls back to the cloud
    client for everyone else.

    Bio auto-pick (v0.2.6): when the paper's content is heavily bio-shaped
    AND the active reviewer pool isn't already a bio-tuned one, swap in
    the bio-research extension's reviewers so a synbio/plant paper gets
    reviewed by Endy/Doudna/Pauly/Mortimer/etc. instead of a generic
    academic panel.
    """
    if agent_log is None:
        agent_log = AgentLog()

    cloud = get_cloud_client()
    if settings.openai_api_key:
        openai_client: Any = OpenAIClient()
    else:
        openai_client = cloud

    reviewers = _select_reviewer_pool(paper_content, agent_log)
    agent_log.add(
        agent="roundtable",
        action="start",
        detail=f"Dispatching {len(reviewers)} reviewers in parallel",
    )

    tasks = []
    for reviewer in reviewers:
        client = openai_client if reviewer.id in _OPENAI_REVIEWER_IDS else cloud
        agent = NamedAgent(f"reviewer_{reviewer.id}", client, agent_log)
        tasks.append(
            _run_single_reviewer(reviewer, agent, paper_content, venue_text, agent_log)
        )

    reviews = await asyncio.gather(*tasks)

    scores = [r["score"] for r in reviews if r["score"] > 0]
    avg = sum(scores) / len(scores) if scores else 0
    agent_log.add(
        agent="roundtable",
        action="complete",
        detail=f"Average score: {avg:.1f}/10 across {len(scores)} reviewers",
        score=round(avg),
    )

    return list(reviews)



# ---------------------------------------------------------------------------
# Bio-domain auto-pick (v0.2.6)
# ---------------------------------------------------------------------------

# Keywords that indicate biological content. Tuned for synbio / molecular
# biology / plant biology / cell wall — the domains the bio-research
# extension reviewers actually critique well. The list is intentionally
# broader than "synbio only" because a Topol or Doudna review adds value
# to clinical / molecular biology papers too.
_BIO_KEYWORDS = frozenset(
    [
        "synbio",
        "synthetic biology",
        "plant",
        "cell wall",
        "polysaccharide",
        "glycan",
        "lignin",
        "cellulose",
        "mannan",
        "mannose",
        "glucan",
        "hemicellulose",
        "biomass",
        "bioenergy",
        "biotech",
        "biotechnology",
        "bioreactor",
        "ferment",
        "metabolic",
        "biosynthesis",
        "enzyme",
        "promoter",
        "vector",
        "plasmid",
        "construct",
        "strain",
        "transformation",
        "transgenic",
        "transformant",
        "agrobacterium",
        "biolistic",
        "cultivar",
        "ecotype",
        "crispr",
        "cas9",
        "guide rna",
        "knockout",
        "knockin",
        "gene expression",
        "transcript",
        "rna-seq",
        "in vivo",
        "in vitro",
        "in planta",
        "phenotype",
        "phenotyping",
        "regeneration",
        "tissue culture",
    ]
)

# Number of distinct keyword hits required to trigger bio swap. Tuned to
# require multiple corroborating signals — a single mention of "plant" or
# "enzyme" shouldn't flip the pool.
_BIO_SWAP_THRESHOLD = 4

# Reviewer IDs that only the bio-research extension declares. If any of
# these appear in the active pool, we're already bio — no need to swap.
_BIO_RESEARCH_REVIEWER_IDS = frozenset(
    [
        "drew_endy",
        "church",
        "keasling",
        "doudna",
        "topol",
        "tim_lu",
        "pauly",
        "mortimer",
        "plant_methods_reviewer",
    ]
)


def _bio_keyword_score(content: str) -> int:
    """Count distinct bio keywords in paper content. Case-insensitive."""
    if not content:
        return 0
    lower = content.lower()
    return sum(1 for kw in _BIO_KEYWORDS if kw in lower)


def _load_bio_research_personas() -> List[Persona]:
    """Load the bio-research extension's research personas directly,
    bypassing the active domain config. Returns [] if the extension
    isn't installed or its YAML is malformed."""
    try:
        for ext in get_all_extensions():
            if ext.manifest.id != "bio-research":
                continue
            for rel_path, yaml_text in ext.personas_files.items():
                # Match anything that looks like the research pool file —
                # the bundled file is "personas/research.yaml" but be
                # forgiving about extension authors' folder conventions.
                if "research" not in rel_path.lower():
                    continue
                data = yaml.safe_load(yaml_text)
                pool = PersonaPool.model_validate(data)
                return list(pool.personas)
    except Exception:
        logger.exception("bio-research persona load failed; falling back to default pool")
    return []


def _select_reviewer_pool(paper_content: str, agent_log: AgentLog) -> List[Persona]:
    """Decide which reviewer pool to dispatch for this paper.

    - If the active "research" pool already contains bio-research
      reviewers (the user is on bio-research extension), use it as-is.
    - Otherwise, score the paper content for bio keywords. If the score
      crosses the threshold, swap in the bio-research extension's pool.
    - Otherwise, use the active pool unchanged.
    """
    default_pool = REVIEWER_REGISTRY.values()
    if not default_pool:
        return default_pool

    active_ids = {p.id for p in default_pool}
    if active_ids & _BIO_RESEARCH_REVIEWER_IDS:
        # Already on a bio pool — nothing to do.
        return default_pool

    score = _bio_keyword_score(paper_content)
    if score < _BIO_SWAP_THRESHOLD:
        return default_pool

    bio_pool = _load_bio_research_personas()
    if not bio_pool:
        return default_pool

    agent_log.add(
        agent="roundtable",
        action="bio_auto_pick",
        detail=(
            f"Paper content scored {score} bio keywords (threshold "
            f"{_BIO_SWAP_THRESHOLD}); swapping in bio-research reviewer "
            f"pool ({len(bio_pool)} reviewers) instead of the active "
            f"domain pool ({len(default_pool)})."
        ),
    )
    return bio_pool


# ---------------------------------------------------------------------------
# Research chat router — selects 3-4 reviewers for a research question
# ---------------------------------------------------------------------------

_RESEARCH_ROUTER_SYSTEM = """You are a routing agent for a research advisory team. Given a researcher's question, \
select 3-4 reviewers whose expertise is most relevant.

Rules:
- Pick 3-4 reviewers (never fewer than 3, never more than 4)
- Match based on expertise, not just keywords
- If the question is broad, pick diverse perspectives

Output ONLY a JSON array of reviewer IDs, ordered by relevance."""


def _default_research_reviewers() -> List[str]:
    """First 3 reviewer IDs from the pool — used when routing fails."""
    return [p.id for p in REVIEWER_REGISTRY.values()][:3]


# Kept for backwards-compat; this is a snapshot of the indie-hacker preset
# defaults, but callers should prefer _default_research_reviewers() at runtime.
DEFAULT_RESEARCH_REVIEWERS = ["technical_rigor", "writing_clarity", "novelty_positioning"]


async def route_to_research_reviewers(user_message: str) -> List[str]:
    """Select 3-4 paper reviewers for a research question."""
    reviewers = REVIEWER_REGISTRY.values()
    reviewer_list = "\n".join(
        f"- {r.id}: {r.focus or r.tagline or r.name}" for r in reviewers
    )
    user_prompt = (
        f"Available reviewers:\n{reviewer_list}\n\n"
        f'Question: "{user_message}"\n\n'
        "Output the JSON array of 3-4 reviewer IDs:"
    )
    try:
        ai = get_cloud_client()
        raw = await ai.complete(system=_RESEARCH_ROUTER_SYSTEM, user=user_prompt)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()
        reviewer_ids = json.loads(cleaned)
        if not isinstance(reviewer_ids, list):
            reviewer_ids = []
        valid_ids = [str(rid) for rid in reviewer_ids if str(rid) in REVIEWER_REGISTRY]
        if len(valid_ids) >= 3:
            return valid_ids[:4]
    except Exception:
        logger.exception("route_to_research_reviewers: router failed, using defaults")
    return _default_research_reviewers()


# ---------------------------------------------------------------------------
# Revision brief builder
# ---------------------------------------------------------------------------


def build_revision_brief(reviews: List[Dict]) -> str:
    """Build a markdown revision brief from roundtable reviews.

    Produces a structured document with per-reviewer summaries and a
    priority-ordered revision guide at the end.
    """
    lines: List[str] = []
    lines.append("# Roundtable Review Summary\n")

    all_critical: List[str] = []
    all_suggestions: List[str] = []

    for review in reviews:
        name = review.get("reviewer_name", "Unknown")
        modeled = review.get("modeled_after", "")
        focus = review.get("focus", "")
        score = review.get("score", 0)

        lines.append(f"## {name} (modeled after {modeled})")
        lines.append(f"**Focus:** {focus}")
        lines.append(f"**Score:** {score}/10\n")

        strengths = review.get("strengths", [])
        if strengths:
            lines.append("**Strengths:**")
            for s in strengths:
                lines.append(f"- {s}")
            lines.append("")

        weaknesses = review.get("weaknesses", [])
        if weaknesses:
            lines.append("**Weaknesses:**")
            for w in weaknesses:
                lines.append(f"- {w}")
            lines.append("")

        suggestions = review.get("suggestions", [])
        if suggestions:
            lines.append("**Suggestions:**")
            for s in suggestions:
                lines.append(f"- {s}")
            lines.append("")

        critical = review.get("critical_issues", [])
        if critical:
            lines.append("**Critical Issues:**")
            for c in critical:
                lines.append(f"- {c}")
            lines.append("")

        for c in critical:
            all_critical.append(f"[{name}] {c}")
        for s in suggestions:
            all_suggestions.append(f"[{name}] {s}")

        lines.append("---\n")

    lines.append("# Priority Revision Guide\n")

    if all_critical:
        lines.append("## Critical Issues (must fix)")
        for i, issue in enumerate(all_critical, 1):
            lines.append(f"{i}. {issue}")
        lines.append("")

    if all_suggestions:
        capped = all_suggestions[:10]
        lines.append("## Suggestions (recommended)")
        for i, sug in enumerate(capped, 1):
            lines.append(f"{i}. {sug}")
        if len(all_suggestions) > 10:
            lines.append(f"\n*({len(all_suggestions) - 10} additional suggestions omitted)*")
        lines.append("")

    scores = [r.get("score", 0) for r in reviews if r.get("score", 0) > 0]
    avg = sum(scores) / len(scores) if scores else 0
    lines.append(f"**Average Score: {avg:.1f}/10**")

    return "\n".join(lines)
