"""methods_drafter — slash_command handler that drafts a Methods section.

v0.2.6 marquee writing feature for the bio researcher use case. The
user types `/draft methods` from the palette (or clicks the action
from the Drafts surface); we query the knowledge graph for the
project's structured lab context — experiments, constructs, strains,
protocols, tool catalogue — and ask the cloud LLM to draft a
publication-style Methods section that **cites the user's actual
infrastructure** (specific constructs, OT-2 protocols, custom GitHub
scripts) instead of generic prose.

Result is persisted as a `BlogPost` with tags `["paper",
"methods_draft"]` so it shows up on the Papers surface next to other
paper-related content. The frontend can `navigate` to the new post
after the trigger succeeds.

Design intent: this handler is the first capability that *consumes*
the bio taxonomy nodes (experiment / construct / strain / protocol /
tool) instead of producing them. Adding more node types to the bio
taxonomy without giving them a consumer leaves them lifeless; this
feature closes the loop.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import BlogPost
from app.models.knowledge import KnowledgeNode
from app.services.ai_client import get_cloud_client
from app.services.egress_recorder import EgressRecorder
from app.services.event_stream import emit

logger = logging.getLogger(__name__)


# Node types the Methods drafter cares about. Order matters — it's
# the order they appear in the prompt context block, with experiments
# leading because they're the most direct "what did we do" anchor.
_CONTEXT_NODE_TYPES = (
    "experiment",
    "construct",
    "strain",
    "protocol",
    "tool",
    "assay",
    "paper_reference",
)

# Per-type cap so a project with hundreds of plasmids doesn't blow
# the prompt window. Tuned to fit comfortably inside Gemini's 1M
# token context with room for the Methods template + instructions.
_PER_TYPE_LIMIT = 20

# Hard cap on the number of nodes pulled total — second safety net.
_TOTAL_NODE_LIMIT = 80


_DEFAULT_METHODS_SYSTEM = """You are a senior scientific editor drafting a Methods section for a peer-reviewed manuscript.

You will receive structured context about the lab's:
- experiments (what was done)
- constructs / plasmids (with registry IDs)
- strains (with schema, parent, resistance markers)
- protocols (with labware, reagents, OT-2 source)
- tools (custom scripts with GitHub URLs)
- reference papers (citation candidates)

Write a Methods section in publication-ready prose. RULES:

1. Cite specific construct names, registry IDs, and protocol names that
   appear in the context — do not invent them. If a construct or
   protocol isn't in the context, say "[CONSTRUCT NAME]" or describe
   the operation without naming.
2. Cite the user's custom tools by their actual GitHub URLs when the
   context provides them (e.g. "sequences were screened using a
   custom Python pipeline available at https://github.com/...").
3. Plant-synbio style: name cultivars/ecotypes precisely, specify
   transformation method (Agrobacterium tumefaciens strain or
   biolistic), selection marker and concentration, regeneration time,
   and validation method (PCR, sequencing, qPCR, metabolite).
4. Statistical methods last paragraph: state N (independent
   transformants AND biological replicates), test used, software,
   significance threshold.
5. Past tense, third person, no first person, no figures, no
   forward-references to results.
6. Subsection headings as bold inline labels (not Markdown headers):
   **Plant material and growth conditions.** **Vector construction.**
   **Plant transformation.** **Genotypic validation.** **Phenotypic
   assays.** **Lab automation.** **Statistical analysis.**

Output ONLY the Methods section text. No preamble, no commentary.
"""

# Style variants the user can pick via config. Each maps to a system
# prompt above; future variants (clinical, materials science, etc.)
# can drop in here without changing the handler.
_STYLE_PROMPTS = {
    "plant_synbio": _DEFAULT_METHODS_SYSTEM,
    "generic": _DEFAULT_METHODS_SYSTEM.replace(
        "Plant-synbio style: name cultivars/ecotypes precisely, specify\n   transformation method (Agrobacterium tumefaciens strain or\n   biolistic), selection marker and concentration, regeneration time,\n   and validation method (PCR, sequencing, qPCR, metabolite).",
        "Use the language of your field — name organisms, strains, cell\n   lines, reagents, and equipment precisely. If something is\n   field-specific (transformation method, dosing schedule, etc.),\n   state it explicitly.",
    ),
}


async def draft_methods_handler(
    payload: Dict[str, Any],
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Dict[str, Any]:
    """Slash-command handler. Reads project context, drafts a Methods
    section, persists it as a BlogPost, returns toast + post id."""
    project_id_raw = payload.get("project_id")
    if not project_id_raw:
        emit("warn", "draft-methods", "draft_methods called without a project_id")
        return {
            "ok": False,
            "toast": "Open a project first — Methods drafter needs project context.",
        }
    try:
        project_id = uuid.UUID(str(project_id_raw))
    except ValueError:
        return {
            "ok": False,
            "toast": f"draft_methods: invalid project_id {project_id_raw!r}",
        }

    style = (payload.get("style") or "plant_synbio").lower()
    system_prompt = _STYLE_PROMPTS.get(style, _STYLE_PROMPTS["plant_synbio"])

    # Pull the structured context out of the knowledge graph. We
    # restrict to (user_id, project_id, archived=False) so the
    # drafter only sees the active lab content for this project.
    nodes_by_type = await _fetch_context_nodes(db, user_id, project_id)
    if not any(nodes_by_type.values()):
        emit(
            "warn",
            "draft-methods",
            f"draft_methods: no lab context found for project {project_id}",
        )
        return {
            "ok": False,
            "toast": (
                "No lab context found yet. Connect Benchling / OT-2 / "
                "GitHub-tools or add experiments to Knowledge first."
            ),
        }

    context_text = _build_context_text(nodes_by_type)

    emit(
        "info",
        "draft-methods",
        f"Drafting Methods section for project {project_id} "
        f"({sum(len(v) for v in nodes_by_type.values())} context nodes, style={style})",
    )

    try:
        ai = get_cloud_client()
        async with EgressRecorder(
            surface="paper",
            service="methods_drafter.draft",
            provider=type(ai).__name__.lower().replace("client", ""),
            model=getattr(ai, "_model", None) or getattr(ai, "chat_model", None),
            user_id=user_id,
            project_id=project_id,
        ) as rec:
            rec.field("system_prompt", system_prompt)
            rec.field("paper_section", "Methods")
            rec.field("context", context_text)
            drafted = await ai.complete(system=system_prompt, user=context_text)
    except Exception as exc:
        logger.exception("draft_methods: cloud LLM call failed")
        emit("error", "draft-methods", f"LLM call failed: {exc}")
        return {"ok": False, "toast": f"Methods drafter failed: {exc}"}

    drafted = (drafted or "").strip()
    if not drafted:
        emit("warn", "draft-methods", "LLM returned an empty Methods draft")
        return {"ok": False, "toast": "Methods drafter returned empty text — try again."}

    # Persist as a BlogPost tagged 'paper' + 'methods_draft' so the
    # Papers surface surfaces it next to other paper-related drafts.
    from datetime import datetime, timezone
    title = f"Methods draft — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    post = BlogPost(
        project_id=project_id,
        title=title,
        content=drafted,
        status="draft",
        tags=["paper", "methods_draft", f"style:{style}"],
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    emit(
        "success",
        "draft-methods",
        f"Methods draft saved as BlogPost {post.id} ({len(drafted)} chars)",
        meta={"post_id": str(post.id), "project_id": str(project_id)},
    )

    return {
        "ok": True,
        "post_id": str(post.id),
        "title": title,
        "char_count": len(drafted),
        "toast": f"Methods draft saved — open Papers to review ({len(drafted)} chars).",
    }


async def _fetch_context_nodes(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Dict[str, List[KnowledgeNode]]:
    """Group recent / non-archived nodes by type for prompt assembly.

    Project-scoped first; if nothing comes back per type, fall back
    to user-scoped (project_id IS NULL) so user-level tool nodes
    (GitHub catalogue) and protocol nodes (OT-2 catalogue) still
    feed the drafter even when they aren't pinned to this project.
    """
    out: Dict[str, List[KnowledgeNode]] = {nt: [] for nt in _CONTEXT_NODE_TYPES}
    total = 0
    for node_type in _CONTEXT_NODE_TYPES:
        if total >= _TOTAL_NODE_LIMIT:
            break
        remaining = min(_PER_TYPE_LIMIT, _TOTAL_NODE_LIMIT - total)
        # Project-scoped first
        stmt = (
            select(KnowledgeNode)
            .where(
                KnowledgeNode.user_id == user_id,
                KnowledgeNode.node_type == node_type,
                KnowledgeNode.archived.is_(False),
            )
            .where(
                (KnowledgeNode.project_id == project_id)
                | (KnowledgeNode.project_id.is_(None))
            )
            .order_by(KnowledgeNode.updated_at.desc())
            .limit(remaining)
        )
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        out[node_type] = rows
        total += len(rows)
    return out


def _build_context_text(nodes_by_type: Dict[str, List[KnowledgeNode]]) -> str:
    """Render the per-type node groups as a prompt block."""
    blocks: List[str] = []
    for node_type, rows in nodes_by_type.items():
        if not rows:
            continue
        header = f"=== {node_type.upper()} ({len(rows)}) ==="
        block_lines = [header]
        for n in rows:
            block_lines.append(f"\n### {n.title}")
            if n.metadata_:
                # Surface the keys most useful for Methods writing —
                # registry IDs, URLs, schema, length, author. The
                # LLM gets the full content too; this just makes the
                # high-signal stuff impossible to miss.
                highlights = {
                    k: n.metadata_.get(k)
                    for k in (
                        "registry_id",
                        "display_id",
                        "github_url",
                        "url",
                        "length_bp",
                        "schema",
                        "api_level",
                        "labware",
                    )
                    if n.metadata_.get(k) not in (None, "", [])
                }
                if highlights:
                    for k, v in highlights.items():
                        block_lines.append(f"- {k}: {v}")
            content = (n.content or "").strip()
            if content:
                # Cap per-node content so a single huge entry doesn't
                # crowd out the rest of the context.
                block_lines.append(content[:1200])
        blocks.append("\n".join(block_lines))
    intro = (
        "Lab context for this project (knowledge graph snapshot). "
        "Use ONLY these names, IDs, and URLs when citing specifics — "
        "do not invent constructs, strains, or protocol names that "
        "aren't listed here.\n\n"
    )
    return intro + "\n\n".join(blocks)
