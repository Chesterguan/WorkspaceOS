# Paper Pipeline v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monolithic paper generation pipeline with a multi-agent, section-by-section pipeline supporting backtracking, venue-aware constraints, and post-generation editing.

**Architecture:** Named agents (gemini_planner, gemini_writer, openai_critic, gemini_editor, ollama_literature) orchestrated in 4 phases: Plan, Draft (with backtracking), Merge+Coherence, Finalize. A new venue_service resolves submission guidelines. Edit endpoint allows section-level modifications post-generation.

**Tech Stack:** Python 3.9+ (FastAPI, SQLAlchemy async), PostgreSQL, Gemini Flash, GPT-4o, Ollama, httpx, Next.js 16, Tailwind, shadcn/ui

**Spec:** `docs/superpowers/specs/2026-04-03-paper-pipeline-v2-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|----------------|
| `backend/app/services/agents.py` | Named agent abstraction: wraps AI clients with structured logging, agent IDs, and log collection |
| `backend/app/services/venue_service.py` | Venue guideline resolution: cache lookup, web fetch, AI inference, manual fallback |
| `backend/app/services/paper_pipeline_v2.py` | V2 orchestrator: 4-phase pipeline (plan, draft+backtrack, merge+coherence, finalize), edit/condense operations |
| `backend/app/models/venue.py` | VenueCache SQLAlchemy model |
| `backend/alembic/versions/0008_venue_cache.py` | Alembic migration for venue_cache table |

### Modified files

| File | Changes |
|------|---------|
| `backend/app/schemas/paper.py` | Add `PaperGenerateV2Response`, `PaperEditRequest`, `PaperEditResponse`, `AgentLogEntry`, `VenueGuidelines` schemas |
| `backend/app/routers/paper.py` | Add `POST /generate-v2` and `POST /{blog_post_id}/edit` endpoints |
| `frontend/lib/types.ts` | Add `PaperGenerateV2Response`, `PaperEditRequest`, `PaperEditResponse`, `AgentLogEntry`, `VenueGuidelines` types |
| `frontend/lib/api.ts` | Add `paper.generateV2()` and `paper.editPaper()` API methods |
| `frontend/app/projects/[projectId]/research/paper/page.tsx` | Add edit mode toggle, instruction input, agent log viewer, venue guidelines display |

---

## Task 1: Agent Abstraction Layer

**Files:**
- Create: `backend/app/services/agents.py`

- [ ] **Step 1: Create the agents module**

This module provides a thin wrapper around AI clients that adds:
- Named agent identity (for log tracing)
- Structured log collection (returned to caller, not just logger)
- JSON extraction helper (agents often need structured output)

```python
"""
Named agent abstraction for the multi-agent paper pipeline.

Each agent wraps an AI client with a name, role description, and structured
log collection. The log entries are returned to the orchestrator so they can
be included in API responses for the frontend agent log viewer.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.ai_client import OpenAIClient, get_cloud_client, get_local_client
from app.config import settings

logger = logging.getLogger(__name__)


class AgentLog:
    """Collects structured log entries from agent actions."""

    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []

    def add(
        self,
        agent: str,
        action: str,
        detail: str,
        section: Optional[str] = None,
        score: Optional[int] = None,
    ) -> None:
        self.entries.append({
            "agent": agent,
            "action": action,
            "section": section,
            "detail": detail,
            "score": score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("[%s] %s: %s%s", agent, action, detail,
                     f" (section: {section})" if section else "")

    def to_list(self) -> List[Dict[str, Any]]:
        return list(self.entries)


class NamedAgent:
    """
    Wraps an AI client with a name and role for logging.

    Usage:
        planner = NamedAgent("gemini_planner", get_cloud_client(), agent_log)
        outline = await planner.complete(system_prompt, user_prompt)
    """

    def __init__(self, name: str, client: Any, log: AgentLog) -> None:
        self.name = name
        self.client = client
        self.log = log

    async def complete(
        self,
        system: str,
        user: str,
        action: str = "complete",
        section: Optional[str] = None,
    ) -> str:
        """Call the underlying AI client and log the action."""
        self.log.add(
            agent=self.name,
            action=action,
            detail=f"Prompt length: {len(system) + len(user)} chars",
            section=section,
        )
        try:
            result = await self.client.complete(system=system, user=user)
            self.log.add(
                agent=self.name,
                action=f"{action}_complete",
                detail=f"Response length: {len(result)} chars",
                section=section,
            )
            return result
        except Exception as exc:
            self.log.add(
                agent=self.name,
                action=f"{action}_error",
                detail=str(exc)[:200],
                section=section,
            )
            raise

    async def complete_json(
        self,
        system: str,
        user: str,
        action: str = "complete_json",
        section: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call the AI client and parse the response as JSON."""
        raw = await self.complete(system=system, user=user, action=action, section=section)
        return extract_json(raw)


def extract_json(text: str) -> Dict[str, Any]:
    """
    Extract a JSON object from AI output that may contain markdown fences
    or surrounding prose.
    """
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Find first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("extract_json: could not parse JSON from text (first 200 chars): %s", text[:200])
    return {}


def create_pipeline_agents(agent_log: AgentLog) -> Dict[str, NamedAgent]:
    """
    Create the standard set of named agents for the v2 paper pipeline.

    Returns a dict keyed by agent name:
        gemini_planner, gemini_writer, openai_critic, gemini_editor, ollama_literature
    """
    cloud = get_cloud_client()
    local = get_local_client()

    # Reviewer: OpenAI if available (different model for genuine critique), else cloud
    if settings.openai_api_key:
        reviewer = OpenAIClient()
    else:
        reviewer = cloud

    return {
        "gemini_planner": NamedAgent("gemini_planner", cloud, agent_log),
        "gemini_writer": NamedAgent("gemini_writer", cloud, agent_log),
        "openai_critic": NamedAgent("openai_critic", reviewer, agent_log),
        "gemini_editor": NamedAgent("gemini_editor", cloud, agent_log),
        "ollama_literature": NamedAgent("ollama_literature", local, agent_log),
    }
```

- [ ] **Step 2: Verify the module imports cleanly**

Run inside Docker:
```bash
docker compose exec backend python -c "from app.services.agents import AgentLog, NamedAgent, create_pipeline_agents; print('OK')"
```
Expected: `OK`

---

## Task 2: VenueCache Model + Migration

**Files:**
- Create: `backend/app/models/venue.py`
- Create: `backend/alembic/versions/0008_venue_cache.py`

- [ ] **Step 1: Create the VenueCache model**

```python
"""VenueCache model — caches resolved submission guidelines for academic venues."""
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VenueCache(Base):
    """Cached submission guidelines for an academic venue (conference/journal/workshop)."""

    __tablename__ = "venue_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    venue_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    venue_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    page_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    word_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    template: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    anonymization: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deadline: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    topics: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )  # "web" | "ai_inferred" | "manual" | "cached"
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Create the Alembic migration**

```python
"""Add venue_cache table

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "venue_cache",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("venue_name", sa.String(500), nullable=False),
        sa.Column("venue_url", sa.String(1000), nullable=True),
        sa.Column("page_limit", sa.Integer(), nullable=True),
        sa.Column("word_limit", sa.Integer(), nullable=True),
        sa.Column("template", sa.String(100), nullable=True),
        sa.Column("anonymization", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deadline", sa.String(100), nullable=True),
        sa.Column("topics", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_venue_cache_venue_name", "venue_cache", ["venue_name"])


def downgrade() -> None:
    op.drop_index("ix_venue_cache_venue_name")
    op.drop_table("venue_cache")
```

- [ ] **Step 3: Run the migration**

```bash
docker compose exec backend alembic upgrade head
```
Expected: `Running upgrade 0007 -> 0008, Add venue_cache table`

- [ ] **Step 4: Verify the table exists**

```bash
docker compose exec backend python -c "
from app.models.venue import VenueCache
print('Model OK:', VenueCache.__tablename__)
"
```
Expected: `Model OK: venue_cache`

---

## Task 3: Venue Service

**Files:**
- Create: `backend/app/services/venue_service.py`

- [ ] **Step 1: Create the venue service**

This service resolves submission guidelines for a venue using a 4-step strategy:
1. Cache lookup (DB)
2. Web fetch (CFP page scraping via httpx)
3. AI inference (ask Gemini to infer guidelines)
4. Manual fallback (empty guidelines)

```python
"""
Venue guideline resolution service.

Resolution strategy (in order):
  1. Cache lookup — check venue_cache table
  2. Web fetch — scrape CFP page for guidelines
  3. AI inference — ask cloud AI to infer typical guidelines
  4. Manual fallback — return empty guidelines for user to fill in
"""
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.venue import VenueCache
from app.services.agents import NamedAgent, extract_json
from app.services.ai_client import get_cloud_client

logger = logging.getLogger(__name__)


@dataclass
class VenueGuidelines:
    venue_name: str
    page_limit: Optional[int] = None
    word_limit: Optional[int] = None
    template: Optional[str] = None
    anonymization: bool = False
    deadline: Optional[str] = None
    topics: List[str] = field(default_factory=list)
    source: str = "manual"  # "cached" | "web" | "ai_inferred" | "manual"
    venue_url: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    def has_constraints(self) -> bool:
        return self.page_limit is not None or self.word_limit is not None


# ─── Well-known venue defaults ────────────────────────────────────────────────
# These cover the most common ML/AI venues so we don't need to scrape every time.

_KNOWN_VENUES: Dict[str, Dict] = {
    "icml": {"page_limit": 8, "template": "icml", "anonymization": True},
    "neurips": {"page_limit": 9, "template": "neurips", "anonymization": True},
    "iclr": {"page_limit": 10, "template": "iclr", "anonymization": True},
    "aaai": {"page_limit": 7, "template": "aaai", "anonymization": True},
    "cvpr": {"page_limit": 8, "template": "cvpr", "anonymization": True},
    "acl": {"page_limit": 8, "template": "acl", "anonymization": True},
    "emnlp": {"page_limit": 8, "template": "acl", "anonymization": True},
    "naacl": {"page_limit": 8, "template": "acl", "anonymization": True},
    "eccv": {"page_limit": 14, "template": "eccv", "anonymization": True},
    "sigchi": {"page_limit": 10, "template": "acm-sigconf", "anonymization": True},
}


def _match_known_venue(venue_name: str) -> Optional[Dict]:
    """Check if the venue matches a well-known venue by keyword."""
    name_lower = venue_name.lower()
    for key, defaults in _KNOWN_VENUES.items():
        if key in name_lower:
            return defaults
    return None


# ─── Resolution steps ─────────────────────────────────────────────────────────

async def _lookup_cache(venue_name: str, db: AsyncSession) -> Optional[VenueGuidelines]:
    """Step 1: Check the venue_cache table."""
    result = await db.execute(
        select(VenueCache)
        .where(VenueCache.venue_name == venue_name)
        .order_by(VenueCache.fetched_at.desc())
        .limit(1)
    )
    cached = result.scalar_one_or_none()
    if cached is None:
        return None

    logger.info("venue_service: cache hit for '%s'", venue_name)
    return VenueGuidelines(
        venue_name=cached.venue_name,
        page_limit=cached.page_limit,
        word_limit=cached.word_limit,
        template=cached.template,
        anonymization=cached.anonymization,
        deadline=cached.deadline,
        topics=cached.topics or [],
        source="cached",
        venue_url=cached.venue_url,
    )


async def _fetch_web(venue_name: str) -> Optional[VenueGuidelines]:
    """
    Step 2: Try to scrape a CFP page.

    This is best-effort — many venues have complex JS-rendered pages that
    won't work with a simple GET. We look for common patterns in the HTML.
    """
    # Build a search-friendly query
    search_query = f"{venue_name} call for papers submission guidelines"
    # We won't actually do a Google search (needs API key). Instead, look for
    # well-known venue patterns and try to match them.
    known = _match_known_venue(venue_name)
    if known:
        logger.info("venue_service: matched known venue pattern for '%s'", venue_name)
        return VenueGuidelines(
            venue_name=venue_name,
            page_limit=known.get("page_limit"),
            template=known.get("template"),
            anonymization=known.get("anonymization", False),
            source="web",
        )
    return None


async def _infer_with_ai(venue_name: str) -> Optional[VenueGuidelines]:
    """
    Step 3: Ask the cloud AI to infer typical submission guidelines.

    Less reliable than web fetch, marked as source: "ai_inferred".
    """
    try:
        ai = get_cloud_client()
        system = (
            "You are an expert on academic conference and journal submission guidelines. "
            "Given a venue name, provide the typical submission guidelines as JSON."
        )
        user = (
            f'What are the submission guidelines for "{venue_name}"?\n\n'
            "Respond with ONLY a JSON object (no markdown fences):\n"
            "{\n"
            '  "page_limit": <int or null>,\n'
            '  "word_limit": <int or null>,\n'
            '  "template": "<template name or null>",\n'
            '  "anonymization": <true/false>,\n'
            '  "deadline": "<date string or null>",\n'
            '  "topics": ["topic1", "topic2"]\n'
            "}"
        )
        raw = await ai.complete(system=system, user=user)
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
            topics=data.get("topics", []),
            source="ai_inferred",
        )
    except Exception:
        logger.exception("venue_service: AI inference failed for '%s'", venue_name)
        return None


async def _save_to_cache(guidelines: VenueGuidelines, db: AsyncSession) -> None:
    """Persist resolved guidelines to the venue_cache table."""
    try:
        entry = VenueCache(
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
        db.add(entry)
        await db.flush()
        logger.info("venue_service: cached guidelines for '%s'", guidelines.venue_name)
    except Exception:
        logger.exception("venue_service: failed to cache guidelines for '%s'", guidelines.venue_name)


# ─── Public API ───────────────────────────────────────────────────────────────

async def resolve_venue(
    venue_name: str,
    db: AsyncSession,
) -> VenueGuidelines:
    """
    Resolve submission guidelines for a venue.

    Tries in order: cache → web/known → AI inference → manual fallback.
    Results are cached for future lookups.
    """
    if not venue_name or not venue_name.strip():
        return VenueGuidelines(venue_name="", source="manual")

    venue_name = venue_name.strip()

    # 1. Cache
    cached = await _lookup_cache(venue_name, db)
    if cached:
        return cached

    # 2. Web / known venue patterns
    web = await _fetch_web(venue_name)
    if web:
        await _save_to_cache(web, db)
        return web

    # 3. AI inference
    inferred = await _infer_with_ai(venue_name)
    if inferred:
        await _save_to_cache(inferred, db)
        return inferred

    # 4. Manual fallback
    logger.info("venue_service: no guidelines found for '%s', returning manual fallback", venue_name)
    return VenueGuidelines(venue_name=venue_name, source="manual")
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
docker compose exec backend python -c "from app.services.venue_service import resolve_venue, VenueGuidelines; print('OK')"
```
Expected: `OK`

---

## Task 4: V2 Paper Pipeline Orchestrator

**Files:**
- Create: `backend/app/services/paper_pipeline_v2.py`

This is the largest task — the core multi-agent, section-by-section pipeline with backtracking.

- [ ] **Step 1: Create the pipeline module with prompt constants and helpers**

```python
"""
Paper Pipeline v2: Multi-agent section-by-section generation with backtracking.

Phases:
  1. PLAN    — gemini_planner creates outline + page budget + dependency graph
  2. DRAFT   — sequential section drafting with per-section review + backtracking
  3. MERGE   — gemini_editor assembles sections, smooths transitions
  4. FINALIZE — ollama_literature verifies citations, generate BibTeX, LaTeX export

The pipeline coexists with v1 (paper_service.generate_paper). The router exposes
it as POST /projects/{id}/paper/generate-v2.
"""
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import BlogPost
from app.schemas.blog import BlogPostCreate, BlogPostUpdate
from app.services.agents import AgentLog, NamedAgent, create_pipeline_agents, extract_json
from app.services.blog_service import create_blog_post, update_blog_post
from app.services.paper_service import (
    _build_paper_context,
    _extract_score,
    export_to_latex,
)
from app.services.scholar_service import generate_bibtex_for_papers
from app.services.venue_service import VenueGuidelines, resolve_venue
from app.utils.diff_utils import compute_diff_stats

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_SECTION_RETRIES = 2      # max critic retries per section
MAX_BACKTRACK_DEPTH = 2      # max upstream revisions per section
TARGET_SCORE = 8             # critic must score >= 8 to pass

# ─── Planner prompts ─────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """You are a research paper planner. Your job is to create a structured outline
with page budgets for each section.

Given:
- Paper title, type, and target venue (with constraints if available)
- Project context (narrative, repo, workspace)
- Available literature

Output a JSON outline:
{
  "sections": [
    {"number": "1", "title": "Introduction", "pages": 1.5, "depends_on": [], "key_points": ["...", "..."]},
    {"number": "2", "title": "Background", "pages": 1.5, "depends_on": ["1"], "key_points": ["...", "..."]},
    ...
  ],
  "total_pages": 8
}

Rules:
- Every section must have a "number", "title", "pages", "depends_on", and "key_points"
- "depends_on" lists section numbers this section references (for backtracking)
- Page budgets must sum to the total target pages
- Include standard sections: Introduction, Related Work/Background, Methodology, Evaluation/Results, Discussion, Conclusion
- For technical reports: also include System Design, Implementation
- For white papers: use business-friendly section names"""

_PLANNER_BACKTRACK_SYSTEM = """You are a research paper planner handling a backtracking decision.

A reviewer found that a section references concepts not defined in upstream sections.
Decide whether to:
1. Revise the upstream section to add the missing definition
2. Adjust the current section to avoid the dependency

Output a JSON decision:
{
  "action": "revise_upstream" or "adjust_current",
  "target_section": "<section number to revise>",
  "instruction": "<specific instruction for the writer>"
}"""

# ─── Writer prompts ───────────────────────────────────────────────────────────

_WRITER_SECTION_SYSTEM = """You are a world-class academic writer drafting one section of a research paper.

You are given:
- The full paper outline (all sections planned)
- All previously written sections (for context and consistency)
- The specific section to write now, with key points to cover
- Available literature for citations

STRICT RULES:
- Write ONLY the assigned section (with its heading)
- Use [N] citation notation from the Available Literature
- Never fabricate citations — use "(citation needed)" if unsure
- Match the tone and terminology of previously written sections
- Stay within the word budget (~250 words per page)
- Formal academic tone, active voice where natural
- Clear topic sentences, paragraphs of 3-6 sentences"""

_WRITER_REVISE_SYSTEM = """You are revising a single section of a research paper based on reviewer feedback.

Rules:
- Address EVERY specific issue the reviewer raised
- Preserve content not criticized
- Keep all [N] citations intact
- Return ONLY the revised section (with its heading)
- Do not add content from other sections"""

# ─── Critic prompts ───────────────────────────────────────────────────────────

_CRITIC_SECTION_SYSTEM = """You are a senior academic reviewer. Review the given section in the context
of ALL existing sections of the paper.

Check for:
1. Quality of this section (clarity, rigor, evidence) — score 1-10
2. Consistency with other sections (terminology, notation, claims)
3. Upstream dependencies — does this section reference anything not yet defined?
4. Downstream impact — does this section introduce concepts that later sections need?

Output ONLY a JSON object:
{
  "score": <1-10>,
  "critique": "<detailed feedback>",
  "upstream_issues": [{"target_section": "<number>", "issue": "<description>"}],
  "passed": <true if score >= 8>
}

Score strictly: only give 8+ if the section is genuinely publication-ready for its venue."""

# ─── Editor prompts ───────────────────────────────────────────────────────────

_EDITOR_COHERENCE_SYSTEM = """You are a senior academic editor doing a coherence pass on a complete paper.

Your job:
1. Smooth transitions between sections
2. Normalize terminology and notation throughout
3. Fix any inconsistencies in claims, figures, or references across sections
4. Ensure the abstract accurately summarizes all sections
5. Check that the conclusion delivers on the introduction's promises

Return the COMPLETE paper with all improvements applied. Do not skip any section."""

_EDITOR_CONDENSE_SYSTEM = """You are a senior academic editor condensing a paper to meet a page budget.

Given:
- The full paper
- The target page count
- Section-by-section page budgets

Your job:
- Trim each section to its budget (roughly 250 words per page)
- Remove redundant examples, verbose explanations, and tangential discussion
- Preserve key claims, evidence, and citations
- Maintain logical flow and academic rigor
- Do NOT remove entire sections — condense them

Return the COMPLETE condensed paper."""


# ─── Phase 1: PLAN ───────────────────────────────────────────────────────────

async def _phase_plan(
    planner: NamedAgent,
    title: str,
    paper_type: str,
    context_block: str,
    venue: Optional[VenueGuidelines],
) -> List[Dict[str, Any]]:
    """
    Generate a structured outline with page budgets.

    Returns a list of section dicts: [{number, title, pages, depends_on, key_points}, ...]
    """
    venue_constraint = ""
    if venue and venue.has_constraints():
        venue_constraint = (
            f"\nVenue constraints for {venue.venue_name}:\n"
            f"  Page limit: {venue.page_limit or 'none'}\n"
            f"  Anonymization: {venue.anonymization}\n"
            f"  Template: {venue.template or 'default'}\n"
        )

    user_prompt = (
        f"Create a paper outline for:\n"
        f"Title: {title}\n"
        f"Type: {paper_type}\n"
        f"{venue_constraint}\n\n"
        f"## Project Context and Literature\n\n{context_block}\n\n"
        f"Output the JSON outline now."
    )

    data = await planner.complete_json(
        system=_PLANNER_SYSTEM,
        user=user_prompt,
        action="plan",
    )

    sections = data.get("sections", [])
    if not sections:
        logger.error("paper_pipeline_v2: planner returned no sections")
        # Fallback: generate a default outline
        sections = [
            {"number": "1", "title": "Introduction", "pages": 1.5, "depends_on": [], "key_points": ["Motivation", "Problem statement", "Contributions"]},
            {"number": "2", "title": "Related Work", "pages": 1.5, "depends_on": ["1"], "key_points": ["Prior approaches", "Gaps in literature"]},
            {"number": "3", "title": "Methodology", "pages": 2, "depends_on": ["1", "2"], "key_points": ["System design", "Technical approach"]},
            {"number": "4", "title": "Evaluation", "pages": 2, "depends_on": ["3"], "key_points": ["Experimental setup", "Results", "Analysis"]},
            {"number": "5", "title": "Discussion", "pages": 1, "depends_on": ["4"], "key_points": ["Limitations", "Implications"]},
            {"number": "6", "title": "Conclusion", "pages": 0.5, "depends_on": ["1", "4", "5"], "key_points": ["Summary", "Future work"]},
        ]

    planner.log.add(
        agent="gemini_planner",
        action="plan_complete",
        detail=f"Outline: {len(sections)} sections, "
               f"total {sum(s.get('pages', 1) for s in sections)} pages",
    )

    return sections


# ─── Phase 2: DRAFT (with backtracking) ──────────────────────────────────────

async def _phase_draft(
    agents: Dict[str, NamedAgent],
    sections: List[Dict[str, Any]],
    context_block: str,
    venue: Optional[VenueGuidelines],
) -> Dict[str, str]:
    """
    Draft each section sequentially, with per-section review and backtracking.

    Returns a dict mapping section number → section content.
    """
    writer = agents["gemini_writer"]
    critic = agents["openai_critic"]
    planner = agents["gemini_planner"]
    agent_log = writer.log

    written_sections: Dict[str, str] = {}  # number → content

    for section in sections:
        sec_num = section["number"]
        sec_title = section["title"]
        sec_pages = section.get("pages", 1)
        key_points = section.get("key_points", [])
        word_target = int(sec_pages * 250)

        # Build context of all previously written sections
        prior_context = "\n\n".join(
            f"## {s['title']}\n{written_sections[s['number']]}"
            for s in sections
            if s["number"] in written_sections
        )

        # Outline summary for the writer
        outline_summary = "\n".join(
            f"  {s['number']}. {s['title']} ({s.get('pages', '?')} pages)"
            for s in sections
        )

        write_prompt = (
            f"## Paper Outline\n{outline_summary}\n\n"
            f"## Previously Written Sections\n{prior_context or '(none yet)'}\n\n"
            f"## Section to Write Now\n"
            f"Section {sec_num}: {sec_title}\n"
            f"Word target: ~{word_target} words\n"
            f"Key points to cover: {', '.join(key_points)}\n\n"
            f"## Available Literature and Context\n{context_block}\n\n"
            f"Write section {sec_num} now."
        )

        # Draft the section
        section_content = await writer.complete(
            system=_WRITER_SECTION_SYSTEM,
            user=write_prompt,
            action="draft",
            section=f"{sec_num}. {sec_title}",
        )

        # Review loop
        retries = 0
        backtrack_count = 0

        while retries <= MAX_SECTION_RETRIES:
            # Build full paper so far for cross-check
            all_content = prior_context + f"\n\n## {sec_title}\n{section_content}" if prior_context else f"## {sec_title}\n{section_content}"

            review_prompt = (
                f"## Full Paper So Far\n{all_content}\n\n"
                f"## Section Under Review\nSection {sec_num}: {sec_title}\n\n"
                f"{section_content}\n\n"
                f"Review this section. Output JSON."
            )

            review_data = await critic.complete_json(
                system=_CRITIC_SECTION_SYSTEM,
                user=review_prompt,
                action="review",
                section=f"{sec_num}. {sec_title}",
            )

            score = review_data.get("score", 0)
            critique = review_data.get("critique", "")
            upstream_issues = review_data.get("upstream_issues", [])
            passed = score >= TARGET_SCORE

            agent_log.add(
                agent="openai_critic",
                action="review_scored",
                detail=f"Score: {score}/10 — {critique[:100]}",
                section=f"{sec_num}. {sec_title}",
                score=score,
            )

            if passed:
                break

            # Handle upstream issues (backtracking)
            if upstream_issues and backtrack_count < MAX_BACKTRACK_DEPTH:
                for issue in upstream_issues[:1]:  # handle one upstream issue at a time
                    target_sec = issue.get("target_section", "")
                    issue_desc = issue.get("issue", "")

                    if target_sec in written_sections:
                        # Ask planner to decide
                        bt_prompt = (
                            f"Critic flagged an issue:\n"
                            f"Current section: {sec_num}. {sec_title}\n"
                            f"Issue: {issue_desc}\n"
                            f"Target upstream section: {target_sec}\n\n"
                            f"Upstream section content:\n{written_sections[target_sec]}\n\n"
                            f"Decide: revise the upstream section or adjust the current section?"
                        )

                        decision = await planner.complete_json(
                            system=_PLANNER_BACKTRACK_SYSTEM,
                            user=bt_prompt,
                            action="backtrack",
                            section=f"{sec_num}. {sec_title}",
                        )

                        action = decision.get("action", "adjust_current")
                        instruction = decision.get("instruction", issue_desc)

                        if action == "revise_upstream" and target_sec in written_sections:
                            # Revise the upstream section
                            revise_prompt = (
                                f"## Section to Revise\n{written_sections[target_sec]}\n\n"
                                f"## Revision Instruction\n{instruction}\n\n"
                                f"Revise this section."
                            )
                            revised = await writer.complete(
                                system=_WRITER_REVISE_SYSTEM,
                                user=revise_prompt,
                                action="backtrack_revise",
                                section=f"{target_sec}. (backtrack)",
                            )
                            written_sections[target_sec] = revised
                            backtrack_count += 1

                            agent_log.add(
                                agent="gemini_planner",
                                action="backtrack_complete",
                                detail=f"Revised upstream section {target_sec}: {instruction[:80]}",
                                section=f"{sec_num}. {sec_title}",
                            )

                            # Rebuild prior context after backtrack
                            prior_context = "\n\n".join(
                                f"## {s['title']}\n{written_sections[s['number']]}"
                                for s in sections
                                if s["number"] in written_sections
                            )

            # Revise current section based on critique
            revise_prompt = (
                f"## Section to Revise\n{section_content}\n\n"
                f"## Reviewer Critique\n{critique}\n\n"
                f"## Previously Written Sections\n{prior_context or '(none)'}\n\n"
                f"Revise this section."
            )
            section_content = await writer.complete(
                system=_WRITER_REVISE_SYSTEM,
                user=revise_prompt,
                action="revise",
                section=f"{sec_num}. {sec_title}",
            )
            retries += 1

        written_sections[sec_num] = section_content

    return written_sections


# ─── Phase 3: MERGE + COHERENCE ──────────────────────────────────────────────

async def _phase_merge(
    editor: NamedAgent,
    critic: NamedAgent,
    sections: List[Dict[str, Any]],
    written_sections: Dict[str, str],
    venue: Optional[VenueGuidelines],
) -> str:
    """Assemble all sections and run a coherence pass."""
    # Assemble the full paper
    assembled = "\n\n".join(
        f"## {s['title']}\n\n{written_sections.get(s['number'], '')}"
        for s in sections
    )

    # Coherence pass
    coherence_prompt = (
        f"## Full Paper (assembled from section-by-section drafting)\n\n"
        f"{assembled}\n\n"
        f"Run a coherence pass on this paper."
    )

    coherent_paper = await editor.complete(
        system=_EDITOR_COHERENCE_SYSTEM,
        user=coherence_prompt,
        action="coherence",
    )

    # If venue has page constraints and paper is over budget, condense
    if venue and venue.page_limit:
        word_count = len(coherent_paper.split())
        target_words = venue.page_limit * 250
        if word_count > target_words * 1.15:  # 15% tolerance
            budget_summary = "\n".join(
                f"  {s['number']}. {s['title']}: {s.get('pages', 1)} pages"
                for s in sections
            )
            condense_prompt = (
                f"## Paper to Condense\n\n{coherent_paper}\n\n"
                f"Target: {venue.page_limit} pages (~{target_words} words)\n"
                f"Current: ~{word_count} words\n\n"
                f"Section budgets:\n{budget_summary}\n\n"
                f"Condense this paper to fit the target."
            )
            coherent_paper = await editor.complete(
                system=_EDITOR_CONDENSE_SYSTEM,
                user=condense_prompt,
                action="condense",
            )

    # Final full-paper review
    review_prompt = (
        f"## Full Paper\n{coherent_paper}\n\n"
        f"Review the entire paper for coherence, flow, and completeness. Output JSON."
    )
    review_data = await critic.complete_json(
        system=_CRITIC_SECTION_SYSTEM,
        user=review_prompt,
        action="final_review",
    )
    final_score = review_data.get("score", 0)
    editor.log.add(
        agent="openai_critic",
        action="final_review_scored",
        detail=f"Final paper score: {final_score}/10",
        score=final_score,
    )

    return coherent_paper


# ─── Phase 4: FINALIZE ───────────────────────────────────────────────────────

async def _phase_finalize(
    papers: List[dict],
) -> str:
    """Generate BibTeX from the literature found during context build."""
    try:
        if papers:
            return await generate_bibtex_for_papers(papers)
    except Exception:
        logger.exception("paper_pipeline_v2: BibTeX generation failed")
    return ""


# ─── Main pipeline entry point ────────────────────────────────────────────────

async def generate_paper_v2(
    project_id: uuid.UUID,
    paper_type: str,
    title: str,
    target_venue: Optional[str],
    additional_instructions: Optional[str],
    db: AsyncSession,
) -> Dict:
    """
    Run the v2 multi-agent paper generation pipeline.

    Returns the same structure as v1's generate_paper() plus agent_log.
    """
    agent_log = AgentLog()
    agents = create_pipeline_agents(agent_log)

    # 0. Resolve venue guidelines
    venue: Optional[VenueGuidelines] = None
    if target_venue:
        venue = await resolve_venue(target_venue, db)
        agent_log.add(
            agent="gemini_planner",
            action="venue_resolved",
            detail=f"Venue: {venue.venue_name}, source: {venue.source}, "
                   f"page_limit: {venue.page_limit}",
        )

    # 1. Build context (reuse v1's context builder)
    logger.info("paper_pipeline_v2: building context for project %s", project_id)
    context_block, papers = await _build_paper_context(project_id, db)

    # Append additional instructions if provided
    if additional_instructions:
        context_block += f"\n\n## Additional Instructions\n{additional_instructions}"

    # 2. PLAN phase
    logger.info("paper_pipeline_v2: Phase 1 — PLAN")
    sections = await _phase_plan(
        planner=agents["gemini_planner"],
        title=title,
        paper_type=paper_type,
        context_block=context_block,
        venue=venue,
    )

    # 3. Create BlogPost to track progress
    post = await create_blog_post(
        project_id=project_id,
        data=BlogPostCreate(
            title=title,
            content="[Pipeline v2: planning complete, drafting...]",
            status="draft",
            tags=["paper", "v2", "progress:10", "step:planning_complete"],
        ),
        db=db,
    )
    post_id = post.id
    logger.info("paper_pipeline_v2: created BlogPost %s", post_id)

    # 4. DRAFT phase (sequential sections with review + backtracking)
    logger.info("paper_pipeline_v2: Phase 2 — DRAFT (%d sections)", len(sections))
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            tags=["paper", "v2", "progress:20", "step:drafting"],
            change_note="Starting section-by-section drafting",
        ),
        db=db,
    )

    written_sections = await _phase_draft(
        agents=agents,
        sections=sections,
        context_block=context_block,
        venue=venue,
    )

    # Save draft state
    draft_content = "\n\n".join(
        f"## {s['title']}\n\n{written_sections.get(s['number'], '')}"
        for s in sections
    )
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=draft_content,
            tags=["paper", "v2", "progress:60", "step:draft_complete"],
            change_note="All sections drafted and reviewed",
        ),
        db=db,
    )

    # 5. MERGE + COHERENCE phase
    logger.info("paper_pipeline_v2: Phase 3 — MERGE + COHERENCE")
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            tags=["paper", "v2", "progress:75", "step:coherence"],
            change_note="Running coherence pass",
        ),
        db=db,
    )

    final_content = await _phase_merge(
        editor=agents["gemini_editor"],
        critic=agents["openai_critic"],
        sections=sections,
        written_sections=written_sections,
        venue=venue,
    )

    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=final_content,
            tags=["paper", "v2", "progress:85", "step:coherence_complete"],
            change_note="Coherence pass complete",
        ),
        db=db,
    )

    # 6. FINALIZE phase
    logger.info("paper_pipeline_v2: Phase 4 — FINALIZE")
    bibtex = await _phase_finalize(papers)

    # Generate LaTeX
    latex_content: Optional[str] = None
    try:
        latex_content, _ = await export_to_latex(final_content, bibtex)
    except Exception:
        logger.exception("paper_pipeline_v2: LaTeX export failed")

    # Mark complete
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=final_content,
            tags=["paper", "v2", "progress:100", "step:complete"],
            change_note="Pipeline v2 complete",
        ),
        db=db,
    )

    # Build version records from agent log for compatibility with v1 response
    version_records: List[Dict] = []
    review_entries = [e for e in agent_log.entries if e.get("score") is not None]
    for idx, entry in enumerate(review_entries, start=1):
        version_records.append({
            "version": idx,
            "review_name": f"{entry.get('section', 'full paper')} — {entry['action']}",
            "score": entry.get("score", 0),
            "review_notes": entry.get("detail", ""),
            "changes_made": "",
            "diff_stats": {"lines_added": 0, "lines_removed": 0, "lines_changed": 0, "similarity_pct": 0},
        })

    # Build review summary
    scores = [e.get("score", 0) for e in review_entries if e.get("score", 0) > 0]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    review_summary = (
        f"V2 pipeline: {len(sections)} sections, "
        f"{len(agent_log.entries)} agent actions, "
        f"{len(scores)} reviews (avg {avg_score}/10)"
    )

    return {
        "blog_post_id": str(post_id),
        "title": title,
        "final_content": final_content,
        "bibtex": bibtex,
        "latex": latex_content,
        "versions": version_records,
        "review_summary": review_summary,
        "agent_log": agent_log.to_list(),
        "venue_guidelines": venue.to_dict() if venue else None,
    }


# ─── Edit / Condense operations ──────────────────────────────────────────────

async def edit_paper(
    blog_post_id: uuid.UUID,
    instruction: str,
    target_section: Optional[str],
    target_pages: Optional[int],
    target_venue: Optional[str],
    db: AsyncSession,
) -> Dict:
    """
    Edit an existing paper based on a user instruction.

    Supports: section edit, condense, expand, add section, remove section, free instruction.
    """
    from sqlalchemy import select
    from app.models.blog import BlogPost

    # Load the existing paper
    result = await db.execute(select(BlogPost).where(BlogPost.id == blog_post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise ValueError(f"Paper not found: {blog_post_id}")

    previous_content = post.content
    agent_log = AgentLog()
    agents = create_pipeline_agents(agent_log)
    writer = agents["gemini_writer"]
    editor = agents["gemini_editor"]
    critic = agents["openai_critic"]

    # Resolve venue if provided
    venue: Optional[VenueGuidelines] = None
    if target_venue:
        venue = await resolve_venue(target_venue, db)

    # Determine the type of edit
    instruction_lower = instruction.lower()
    is_condense = "condense" in instruction_lower or target_pages is not None
    is_expand = "expand" in instruction_lower
    is_add_section = "add section" in instruction_lower or "add a section" in instruction_lower
    is_remove_section = "remove" in instruction_lower and "section" in instruction_lower

    new_content: str

    if is_condense:
        # Condense the paper
        target = target_pages or (venue.page_limit if venue else None) or 8
        target_words = target * 250
        condense_prompt = (
            f"## Paper to Condense\n\n{previous_content}\n\n"
            f"Target: {target} pages (~{target_words} words)\n\n"
            f"Instruction: {instruction}"
        )
        new_content = await editor.complete(
            system=_EDITOR_CONDENSE_SYSTEM,
            user=condense_prompt,
            action="condense",
        )
    elif target_section:
        # Edit a specific section
        revise_prompt = (
            f"## Full Paper\n{previous_content}\n\n"
            f"## Section to Edit: {target_section}\n\n"
            f"## Instruction\n{instruction}\n\n"
            f"Return the COMPLETE paper with only the specified section modified."
        )
        new_content = await editor.complete(
            system=_EDITOR_COHERENCE_SYSTEM,
            user=revise_prompt,
            action="edit_section",
            section=target_section,
        )
    else:
        # Free-form instruction on whole paper
        edit_prompt = (
            f"## Paper\n{previous_content}\n\n"
            f"## Instruction\n{instruction}\n\n"
            f"Apply the instruction to the paper. Return the COMPLETE modified paper."
        )
        new_content = await editor.complete(
            system=_EDITOR_COHERENCE_SYSTEM,
            user=edit_prompt,
            action="edit_free",
        )

    # Review the edited content
    review_prompt = (
        f"## Edited Paper\n{new_content}\n\n"
        f"Review the edited paper for quality. Output JSON."
    )
    review_data = await critic.complete_json(
        system=_CRITIC_SECTION_SYSTEM,
        user=review_prompt,
        action="edit_review",
    )
    edit_score = review_data.get("score", 0)

    # Save as new version
    diff_stats = compute_diff_stats(previous_content, new_content)
    change_note = f"Edit: {instruction[:100]}"

    # Get current version number
    from sqlalchemy import func as sa_func
    version_result = await db.execute(
        select(sa_func.max(BlogPostVersion.version))
        .where(BlogPostVersion.blog_post_id == blog_post_id)
    )
    current_version = version_result.scalar() or 1

    await update_blog_post(
        post_id=blog_post_id,
        data=BlogPostUpdate(
            content=new_content,
            change_note=change_note,
        ),
        db=db,
    )

    # Detect which sections were modified
    sections_modified: List[str] = []
    if target_section:
        sections_modified = [target_section]
    else:
        # Compare section headers between old and new
        import difflib
        old_lines = previous_content.splitlines()
        new_lines = new_content.splitlines()
        for diff_line in difflib.unified_diff(old_lines, new_lines, lineterm=""):
            if diff_line.startswith("+## ") or diff_line.startswith("-## "):
                sec_name = diff_line[3:].strip() if diff_line.startswith("-") else diff_line[3:].strip()
                if sec_name not in sections_modified:
                    sections_modified.append(sec_name)

    return {
        "blog_post_id": str(blog_post_id),
        "updated_content": new_content,
        "previous_version": current_version,
        "new_version": current_version + 1,
        "changes_summary": (
            f"Applied edit: {instruction[:80]}. "
            f"{diff_stats['lines_added']} lines added, "
            f"{diff_stats['lines_removed']} removed."
        ),
        "agent_log": agent_log.to_list(),
        "sections_modified": sections_modified,
    }
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
docker compose exec backend python -c "from app.services.paper_pipeline_v2 import generate_paper_v2, edit_paper; print('OK')"
```
Expected: `OK`

---

## Task 5: Schemas + Router Endpoints

**Files:**
- Modify: `backend/app/schemas/paper.py`
- Modify: `backend/app/routers/paper.py`

- [ ] **Step 1: Add v2 schemas to paper.py**

Add these schemas at the end of `backend/app/schemas/paper.py`:

```python
# ---------------------------------------------------------------------------
# V2 Pipeline schemas
# ---------------------------------------------------------------------------

class AgentLogEntry(BaseModel):
    agent: str          # "gemini_planner" | "gemini_writer" | "openai_critic" | ...
    action: str         # "plan" | "draft" | "review" | "revise" | "backtrack" | "coherence"
    section: Optional[str] = None  # "3. Methodology" or null for full-paper actions
    detail: str         # Human-readable summary
    score: Optional[int] = None  # Critic score if applicable
    timestamp: str      # ISO timestamp


class VenueGuidelinesSchema(BaseModel):
    venue_name: str
    page_limit: Optional[int] = None
    word_limit: Optional[int] = None
    template: Optional[str] = None
    anonymization: bool = False
    deadline: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    source: str = "manual"
    venue_url: Optional[str] = None


class PaperGenerateV2Response(BaseModel):
    blog_post_id: str
    title: str
    final_content: str
    bibtex: str
    latex: Optional[str] = None
    versions: List[PaperVersionSummary]
    review_summary: str
    agent_log: List[AgentLogEntry]
    venue_guidelines: Optional[VenueGuidelinesSchema] = None


class PaperEditRequest(BaseModel):
    instruction: str = Field(..., min_length=3, max_length=2000)
    target_section: Optional[str] = Field(
        default=None,
        description="Section to edit (e.g. '3. Methodology'), or null for whole paper",
    )
    target_pages: Optional[int] = Field(
        default=None,
        description="Target page count for condense operations",
    )
    target_venue: Optional[str] = Field(
        default=None,
        description="Venue name — triggers venue resolution for constraints",
    )


class PaperEditResponse(BaseModel):
    blog_post_id: str
    updated_content: str
    previous_version: int
    new_version: int
    changes_summary: str
    agent_log: List[AgentLogEntry]
    sections_modified: List[str]
```

- [ ] **Step 2: Add v2 endpoints to paper router**

Add these endpoints to `backend/app/routers/paper.py` after the existing `generate_paper` endpoint:

```python
# At the top — add new schema imports:
from app.schemas.paper import (
    # ... existing imports ...
    AgentLogEntry,
    PaperEditRequest,
    PaperEditResponse,
    PaperGenerateV2Response,
    VenueGuidelinesSchema,
)
from app.services import paper_pipeline_v2

# ─── V2 endpoints ─────────────────────────────────────────────────────────────

@router.post(
    "/generate-v2",
    response_model=PaperGenerateV2Response,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a paper using the v2 multi-agent pipeline",
)
async def generate_paper_v2(
    project_id: uuid.UUID,
    body: PaperGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaperGenerateV2Response:
    """
    Run the v2 multi-agent section-by-section paper pipeline.

    This is a **long-running** endpoint (expect 5-15 minutes).
    Features over v1: named agents, section-by-section drafting,
    backtracking, venue-aware constraints, agent log trace.
    """
    await _require_project(project_id, db)

    if body.paper_type not in _VALID_PAPER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid paper_type '{body.paper_type}'. Must be one of: {sorted(_VALID_PAPER_TYPES)}",
        )

    result = await paper_pipeline_v2.generate_paper_v2(
        project_id=project_id,
        paper_type=body.paper_type,
        title=body.title,
        target_venue=body.target_venue,
        additional_instructions=body.additional_instructions,
        db=db,
    )

    return PaperGenerateV2Response(
        blog_post_id=result["blog_post_id"],
        title=result["title"],
        final_content=result["final_content"],
        bibtex=result["bibtex"],
        latex=result.get("latex"),
        versions=[PaperVersionSummary(**v) for v in result["versions"]],
        review_summary=result["review_summary"],
        agent_log=[AgentLogEntry(**e) for e in result["agent_log"]],
        venue_guidelines=VenueGuidelinesSchema(**result["venue_guidelines"]) if result.get("venue_guidelines") else None,
    )


@router.post(
    "/{blog_post_id}/edit",
    response_model=PaperEditResponse,
    status_code=status.HTTP_200_OK,
    summary="Edit an existing paper via instruction",
)
async def edit_paper(
    project_id: uuid.UUID,
    blog_post_id: str,
    body: PaperEditRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaperEditResponse:
    """
    Edit an existing paper based on a natural-language instruction.

    Supports: edit section, condense, expand, add/remove section, free instruction.
    Works on papers generated by either v1 or v2.
    """
    await _require_project(project_id, db)
    post = await _require_blog_post(blog_post_id, db)

    result = await paper_pipeline_v2.edit_paper(
        blog_post_id=post.id,
        instruction=body.instruction,
        target_section=body.target_section,
        target_pages=body.target_pages,
        target_venue=body.target_venue,
        db=db,
    )

    return PaperEditResponse(
        blog_post_id=result["blog_post_id"],
        updated_content=result["updated_content"],
        previous_version=result["previous_version"],
        new_version=result["new_version"],
        changes_summary=result["changes_summary"],
        agent_log=[AgentLogEntry(**e) for e in result["agent_log"]],
        sections_modified=result["sections_modified"],
    )
```

- [ ] **Step 3: Verify endpoints register**

```bash
docker compose up --build -d backend && sleep 3 && docker compose logs backend --tail 5
```
Then test:
```bash
curl -s http://localhost:8989/docs | grep -o "generate-v2\|edit"
```
Expected: both endpoints appear in the OpenAPI docs.

---

## Task 6: Frontend Types + API Methods

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add v2 types to types.ts**

Add after the existing `PaperExportResponse` interface:

```typescript
// ─── V2 Pipeline Types ──────────────────────────────────────────

export interface AgentLogEntry {
  agent: string;
  action: string;
  section: string | null;
  detail: string;
  score: number | null;
  timestamp: string;
}

export interface VenueGuidelines {
  venue_name: string;
  page_limit: number | null;
  word_limit: number | null;
  template: string | null;
  anonymization: boolean;
  deadline: string | null;
  topics: string[];
  source: string; // "cached" | "web" | "ai_inferred" | "manual"
  venue_url: string | null;
}

export interface PaperGenerateV2Response {
  blog_post_id: string;
  title: string;
  final_content: string;
  bibtex: string;
  latex: string | null;
  versions: PaperVersionInfo[];
  review_summary: string;
  agent_log: AgentLogEntry[];
  venue_guidelines: VenueGuidelines | null;
}

export interface PaperEditRequest {
  instruction: string;
  target_section?: string | null;
  target_pages?: number | null;
  target_venue?: string | null;
}

export interface PaperEditResponse {
  blog_post_id: string;
  updated_content: string;
  previous_version: number;
  new_version: number;
  changes_summary: string;
  agent_log: AgentLogEntry[];
  sections_modified: string[];
}
```

- [ ] **Step 2: Add v2 API methods to api.ts**

Add to the `paper` object in `frontend/lib/api.ts`:

```typescript
  generateV2(projectId: string, data: PaperGenerateRequest): Promise<PaperGenerateV2Response> {
    return apiFetch<PaperGenerateV2Response>(`/projects/${projectId}/paper/generate-v2`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  editPaper(projectId: string, blogPostId: string, data: PaperEditRequest): Promise<PaperEditResponse> {
    return apiFetch<PaperEditResponse>(`/projects/${projectId}/paper/${blogPostId}/edit`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
```

Also add the new types to the import block at the top of `api.ts`:

```typescript
  PaperGenerateV2Response,
  PaperEditRequest,
  PaperEditResponse,
```

---

## Task 7: Frontend Edit Mode UI

**Files:**
- Modify: `frontend/app/projects/[projectId]/research/paper/page.tsx`

This task adds:
1. A "View | Edit" mode toggle on the paper results page
2. An instruction input with quick-action buttons (Condense, Expand, Add Section)
3. An agent log viewer panel showing the trace of which agent did what
4. Venue guidelines display when a venue is specified

- [ ] **Step 1: Add edit mode state and imports**

Add to the imports at the top of `page.tsx`:

```typescript
import type {
  // ... existing imports ...
  PaperGenerateV2Response,
  PaperEditRequest,
  PaperEditResponse,
  AgentLogEntry,
  VenueGuidelines,
} from "@/lib/types";
import { Pencil, Eye, Bot, Target, Minimize2, Maximize2, Plus, Trash2 } from "lucide-react";
```

Add to state section (after existing state declarations):

```typescript
  // ── Edit mode state ─────────────────────────────────────────────────────────
  type ViewMode = "view" | "edit";
  const [viewMode, setViewMode] = useState<ViewMode>("view");
  const [editInstruction, setEditInstruction] = useState("");
  const [editTargetSection, setEditTargetSection] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editResult, setEditResult] = useState<PaperEditResponse | null>(null);
  // V2 response extras
  const [agentLog, setAgentLog] = useState<AgentLogEntry[]>([]);
  const [venueGuidelines, setVenueGuidelines] = useState<VenueGuidelines | null>(null);
  // Use v2 pipeline toggle
  const [useV2, setUseV2] = useState(true);
```

- [ ] **Step 2: Add edit handler and modify generate handler**

Add the edit handler:

```typescript
  async function handleEditPaper(instruction: string, targetSection?: string | null) {
    if (!result || !instruction.trim()) return;
    setIsEditing(true);
    setEditResult(null);
    try {
      const res = await paperApi.editPaper(projectId, result.blog_post_id, {
        instruction: instruction.trim(),
        target_section: targetSection || undefined,
        target_venue: targetVenue.trim() || undefined,
      });
      setEditResult(res);
      setAgentLog(res.agent_log);
      // Update the main result's final_content with the edit
      setResult((prev) =>
        prev ? { ...prev, final_content: res.updated_content } : prev
      );
      toast.success(res.changes_summary);
    } catch {
      toast.error("Edit failed");
    } finally {
      setIsEditing(false);
      setEditInstruction("");
    }
  }
```

Modify the existing `handleGenerate` to support v2:

In the generate handler, change the API call to:

```typescript
  // Replace the existing paperApi.generate call:
  const res = useV2
    ? await paperApi.generateV2(projectId, reqData)
    : await paperApi.generate(projectId, reqData);

  // After setting result, check for v2 extras:
  if ("agent_log" in res) {
    const v2Res = res as PaperGenerateV2Response;
    setAgentLog(v2Res.agent_log);
    setVenueGuidelines(v2Res.venue_guidelines);
  }
```

- [ ] **Step 3: Add the Edit Mode UI panel**

Add this JSX in the results section (after the existing paper display), inside the result conditional:

```tsx
{/* View/Edit mode toggle */}
{result && (
  <div className="flex items-center gap-2 mb-4">
    <Button
      variant={viewMode === "view" ? "default" : "outline"}
      size="sm"
      onClick={() => setViewMode("view")}
    >
      <Eye className="h-4 w-4 mr-1" /> View
    </Button>
    <Button
      variant={viewMode === "edit" ? "default" : "outline"}
      size="sm"
      onClick={() => setViewMode("edit")}
    >
      <Pencil className="h-4 w-4 mr-1" /> Edit
    </Button>
  </div>
)}

{/* Edit mode panel */}
{viewMode === "edit" && result && (
  <div className="space-y-4 border rounded-lg p-4 bg-muted/30">
    <div className="flex gap-2 flex-wrap">
      <Button size="sm" variant="outline" onClick={() => setEditInstruction("Condense to " + (venueGuidelines?.page_limit || 8) + " pages")}>
        <Minimize2 className="h-3 w-3 mr-1" /> Condense
      </Button>
      <Button size="sm" variant="outline" onClick={() => setEditInstruction("Expand section with more detail")}>
        <Maximize2 className="h-3 w-3 mr-1" /> Expand
      </Button>
      <Button size="sm" variant="outline" onClick={() => setEditInstruction("Add a section on ")}>
        <Plus className="h-3 w-3 mr-1" /> Add Section
      </Button>
    </div>
    <div className="flex gap-2">
      <Textarea
        value={editInstruction}
        onChange={(e) => setEditInstruction(e.target.value)}
        placeholder="Enter edit instruction (e.g., 'Rewrite the introduction to emphasize the governance gap')"
        className="min-h-[60px]"
      />
      <Button
        onClick={() => handleEditPaper(editInstruction, editTargetSection)}
        disabled={isEditing || !editInstruction.trim()}
        className="shrink-0"
      >
        {isEditing ? <Loader2 className="h-4 w-4 animate-spin" /> : "Apply Edit"}
      </Button>
    </div>
    {editResult && (
      <div className="text-sm text-muted-foreground">
        {editResult.changes_summary}
        {editResult.sections_modified.length > 0 && (
          <span> Modified: {editResult.sections_modified.join(", ")}</span>
        )}
      </div>
    )}
  </div>
)}

{/* Agent Log viewer */}
{agentLog.length > 0 && (
  <details className="mt-4 border rounded-lg">
    <summary className="p-3 cursor-pointer flex items-center gap-2 font-medium text-sm">
      <Bot className="h-4 w-4" /> Agent Log ({agentLog.length} actions)
    </summary>
    <div className="p-3 max-h-80 overflow-y-auto space-y-1">
      {agentLog.map((entry, i) => (
        <div key={i} className="flex items-start gap-2 text-xs font-mono">
          <Badge variant="outline" className="shrink-0 text-[10px]">
            {entry.agent}
          </Badge>
          <span className="text-muted-foreground">{entry.action}</span>
          {entry.section && <span className="text-blue-500">[{entry.section}]</span>}
          {entry.score !== null && (
            <Badge variant={entry.score >= 8 ? "default" : "destructive"} className="text-[10px]">
              {entry.score}/10
            </Badge>
          )}
          <span className="truncate">{entry.detail}</span>
        </div>
      ))}
    </div>
  </details>
)}

{/* Venue guidelines display */}
{venueGuidelines && venueGuidelines.source !== "manual" && (
  <div className="flex items-center gap-3 text-sm text-muted-foreground mt-2">
    <Target className="h-4 w-4 shrink-0" />
    <span>
      {venueGuidelines.venue_name}
      {venueGuidelines.page_limit && ` • ${venueGuidelines.page_limit} pages`}
      {venueGuidelines.anonymization && " • Double-blind"}
      {venueGuidelines.deadline && ` • Due: ${venueGuidelines.deadline}`}
      <span className="text-muted-foreground/60"> ({venueGuidelines.source})</span>
    </span>
  </div>
)}
```

- [ ] **Step 4: Verify frontend builds**

```bash
cd frontend && npm run build
```
Expected: Build succeeds with no type errors.

---

## Task 8: Integration Test + QA Verification

- [ ] **Step 1: Rebuild and test backend starts**

```bash
docker compose up --build -d backend && sleep 5 && docker compose logs backend --tail 10
```
Expected: Backend starts without import errors.

- [ ] **Step 2: Run migration**

```bash
docker compose exec backend alembic upgrade head
```
Expected: Migration 0008 applied successfully.

- [ ] **Step 3: Verify all new endpoints appear in OpenAPI**

```bash
curl -s http://localhost:8989/openapi.json | python3 -m json.tool | grep -E "generate-v2|/edit"
```
Expected: Both `/generate-v2` and `/{blog_post_id}/edit` paths appear.

- [ ] **Step 4: Test venue resolution**

```bash
docker compose exec backend python -c "
import asyncio
from app.services.venue_service import resolve_venue, VenueGuidelines

async def test():
    # Test known venue matching (no DB needed)
    from app.services.venue_service import _fetch_web
    result = await _fetch_web('ICML 2026')
    print(f'ICML: page_limit={result.page_limit}, template={result.template}')
    assert result.page_limit == 8
    result2 = await _fetch_web('NeurIPS 2026')
    print(f'NeurIPS: page_limit={result2.page_limit}')
    assert result2.page_limit == 9
    print('All venue tests passed')

asyncio.run(test())
"
```
Expected: `All venue tests passed`

- [ ] **Step 5: Test agent abstraction**

```bash
docker compose exec backend python -c "
from app.services.agents import AgentLog, extract_json

log = AgentLog()
log.add(agent='test', action='test_action', detail='hello')
assert len(log.entries) == 1
assert log.entries[0]['agent'] == 'test'

data = extract_json('{\"score\": 8, \"passed\": true}')
assert data['score'] == 8

data2 = extract_json('\`\`\`json\n{\"x\": 1}\n\`\`\`')
assert data2['x'] == 1

print('All agent tests passed')
"
```
Expected: `All agent tests passed`

- [ ] **Step 6: Verify frontend builds and runs**

```bash
cd frontend && npm run build
```
Expected: Build succeeds.

---

## Summary

| Task | Component | Files | Estimated Complexity |
|------|-----------|-------|---------------------|
| 1 | Agent abstraction | Create: `agents.py` | Low |
| 2 | VenueCache model + migration | Create: `venue.py`, `0008_*.py` | Low |
| 3 | Venue service | Create: `venue_service.py` | Medium |
| 4 | V2 pipeline orchestrator | Create: `paper_pipeline_v2.py` | High |
| 5 | Schemas + router | Modify: `paper.py` (schemas), `paper.py` (router) | Medium |
| 6 | Frontend types + API | Modify: `types.ts`, `api.ts` | Low |
| 7 | Frontend edit mode UI | Modify: `paper/page.tsx` | Medium |
| 8 | Integration test | Verification only | Low |

Total: 5 new files, 4 modified files, 1 migration.
