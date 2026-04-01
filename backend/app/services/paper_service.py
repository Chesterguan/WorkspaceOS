"""
Multi-pass academic paper writing pipeline.

Pipeline
--------
1. DRAFT  — Generate a full paper from project context + literature (cloud AI / Gemini)
2. REVIEW 1 — Technical soundness (OpenAI reviewer)  → Writer revises (Gemini)
3. REVIEW 2 — Novelty & positioning                  → Writer revises
4. REVIEW 3 — Writing quality                        → Writer revises
5. REVIEW 4 — Citation audit                         → Writer revises
6. REVIEW 5 — Final polish                           → Final version stored

Each revision is snapshotted as a BlogPostVersion so the UI can show diffs and
the user can revert. Progress is tracked via BlogPost.tags so the frontend can poll.

AI provider split (matches the rest of the codebase):
  - Cloud client (Gemini by default) → writer / drafting
  - OpenAI client → peer-reviewer critique (separate config key)

Pandoc is used for LaTeX export when available; a pure-Python fallback is used
otherwise so the feature always works.
"""
import logging
import re
import subprocess
import tempfile
import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import BlogPost, BlogPostVersion
from app.models.project import Project
from app.schemas.blog import BlogPostCreate, BlogPostUpdate
from app.services.ai_client import get_cloud_client, get_local_client
from app.services.blog_service import create_blog_post, get_version_chain, update_blog_post
from app.services.narrative_service import build_context_block, get_or_create
from app.services.repo_context import get_generation_context
from app.services.scholar_service import (
    find_related_work,
    format_papers_for_prompt,
    generate_bibtex_for_papers,
)
from app.services.workspace_scanner import get_latest_snapshot
from app.utils.diff_utils import compute_diff_stats

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Review pass definitions
# ---------------------------------------------------------------------------

REVIEW_PASSES: List[Dict] = [
    {
        "name": "Technical Soundness",
        "system": (
            "You are a senior academic reviewer evaluating a paper for technical soundness.\n"
            "Review for:\n"
            "1. Is the methodology clearly described and reproducible?\n"
            "2. Are claims supported by evidence (citations, data, or logical argument)?\n"
            "3. Are there logical gaps in the argument?\n"
            "4. Is the experimental design (if any) appropriate?\n"
            "5. Are limitations acknowledged?\n"
            "Score 1-10. List specific issues with line references. Be constructive but rigorous.\n"
            "End your review with exactly: Score: N (where N is 1-10)"
        ),
    },
    {
        "name": "Novelty & Positioning",
        "system": (
            "You are a reviewer evaluating novelty and literature positioning.\n"
            "Review for:\n"
            "1. Is the contribution clearly stated and genuinely novel?\n"
            "2. Is related work comprehensive and fairly compared?\n"
            "3. Is the paper positioned correctly in the field?\n"
            "4. Are there important missing references?\n"
            "5. Does the paper make clear what's new vs. what's existing?\n"
            "Score 1-10. List specific improvements needed.\n"
            "End your review with exactly: Score: N (where N is 1-10)"
        ),
    },
    {
        "name": "Writing Quality",
        "system": (
            "You are an academic writing editor reviewing for clarity and presentation.\n"
            "Review for:\n"
            "1. Is the abstract self-contained and compelling?\n"
            "2. Does each section flow logically to the next?\n"
            "3. Are there unclear sentences, jargon, or ambiguity?\n"
            "4. Is the paper the right length for its venue?\n"
            "5. Are figures/tables referenced and explained in text?\n"
            "Score 1-10. Quote specific passages that need rewriting.\n"
            "End your review with exactly: Score: N (where N is 1-10)"
        ),
    },
    {
        "name": "Citation Audit",
        "system": (
            "You are a citation auditor checking reference integrity.\n"
            "Review for:\n"
            "1. Does every factual claim have a citation?\n"
            "2. Are all cited references real papers (check the reference list)?\n"
            "3. Are there self-citations that should be diversified?\n"
            "4. Are citations used correctly (not misrepresenting the cited work)?\n"
            "5. Is the reference list properly formatted?\n"
            "Flag any citation that looks fabricated or misattributed.\n"
            "End your review with exactly: Score: N (where N is 1-10)"
        ),
    },
    {
        "name": "Final Polish",
        "system": (
            "You are doing a final quality check before submission.\n"
            "Review for:\n"
            "1. Does the title accurately reflect the content?\n"
            "2. Does the abstract match the actual paper content?\n"
            "3. Does the conclusion align with the introduction's promises?\n"
            "4. Are all acronyms defined on first use?\n"
            "5. Is formatting consistent throughout?\n"
            "6. Are there any remaining typos, grammar issues, or formatting problems?\n"
            "Make final micro-edits. This is the last pass before submission.\n"
            "End your review with exactly: Score: N (where N is 1-10)"
        ),
    },
]

# ---------------------------------------------------------------------------
# Paper type → venue hint mapping
# ---------------------------------------------------------------------------

_PAPER_TYPE_HINTS: Dict[str, str] = {
    "conference": (
        "a peer-reviewed conference paper (typical length: 8-12 pages). "
        "Include: Abstract, Introduction, Related Work, Methodology, "
        "Experiments/Evaluation, Discussion, Conclusion, References."
    ),
    "journal": (
        "a full journal article (typical length: 15-25 pages). "
        "Include: Abstract, Introduction, Background, Methodology, "
        "Results, Discussion, Conclusion, References. "
        "Journal papers require more thorough related work and deeper analysis than conference papers."
    ),
    "technical_report": (
        "a technical report (no page limit). "
        "Include: Executive Summary, Introduction, Background and Related Work, "
        "System Design, Implementation, Evaluation, Discussion, Conclusion, References."
    ),
    "white_paper": (
        "an industry white paper for a non-academic audience. "
        "Include: Executive Summary, Problem Statement, Solution Overview, "
        "Technical Approach, Evidence and Results, Call to Action, References. "
        "Avoid jargon. Lead with value, not with methodology."
    ),
}


# ---------------------------------------------------------------------------
# Context assembly (reuses the same pattern as research_service.py)
# ---------------------------------------------------------------------------

async def _build_paper_context(
    project_id: uuid.UUID,
    db: AsyncSession,
) -> Tuple[str, List[dict]]:
    """
    Build the full context string and raw papers list for the paper draft.

    Returns: (context_block: str, papers: List[dict])
    The papers list is kept separately so we can call generate_bibtex_for_papers() later.
    """
    sections: List[str] = []
    papers: List[dict] = []
    narrative_ctx: dict = {}

    # -- Narrative --
    try:
        narrative = await get_or_create(project_id, db)
        narrative_ctx = build_context_block(narrative)
        parts: List[str] = []
        if narrative_ctx.get("one_liner"):
            parts.append(f"One-liner: {narrative_ctx['one_liner']}")
        if narrative_ctx.get("target_audience"):
            parts.append(f"Target audience: {narrative_ctx['target_audience']}")
        if narrative_ctx.get("origin_story"):
            parts.append(f"Origin story / motivation: {narrative_ctx['origin_story']}")
        if narrative_ctx.get("preferred_angles"):
            parts.append(f"Research angles: {', '.join(narrative_ctx['preferred_angles'])}")
        if parts:
            sections.append("## Project Narrative\n" + "\n".join(parts))
    except Exception:
        logger.exception("paper_service: failed to load narrative for project %s", project_id)

    # -- GitHub repo context --
    try:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project and project.github_repo:
            repo_ctx = await get_generation_context(project.github_repo, is_private=False)
            if repo_ctx and repo_ctx.strip():
                if len(repo_ctx) > 8000:
                    repo_ctx = repo_ctx[:8000] + "\n\n[... truncated ...]"
                sections.append(f"## Repository Context (architecture/methods)\n{repo_ctx}")
    except Exception:
        logger.exception("paper_service: failed to load repo context for project %s", project_id)

    # -- Workspace snapshot --
    try:
        snapshot = await get_latest_snapshot(project_id, db)
        if snapshot:
            ws_parts = [snapshot.summary]
            if snapshot.git_branch:
                ws_parts.append(f"Current branch: {snapshot.git_branch}")
            sections.append(
                "## Local Workspace\n" + "\n".join(ws_parts)
            )
    except Exception:
        logger.exception("paper_service: failed to load workspace for project %s", project_id)

    # -- Literature (Semantic Scholar) --
    try:
        # Extract keywords from narrative for lit search
        keywords: List[str] = []
        if narrative_ctx.get("one_liner"):
            keywords.append(narrative_ctx["one_liner"])
        if narrative_ctx.get("origin_story"):
            first_sent = narrative_ctx["origin_story"].split(".")[0].strip()
            if first_sent and len(first_sent) > 10:
                keywords.append(first_sent[:120])
        for angle in (narrative_ctx.get("preferred_angles") or [])[:2]:
            if angle:
                keywords.append(str(angle))

        if keywords:
            papers = await find_related_work(keywords, limit=20)
            if papers:
                sections.append(format_papers_for_prompt(papers))
    except Exception:
        logger.exception("paper_service: Semantic Scholar search failed for project %s", project_id)

    return "\n\n".join(sections), papers


# ---------------------------------------------------------------------------
# Draft generation prompt
# ---------------------------------------------------------------------------

_WRITER_SYSTEM = """You are a world-class academic writer producing a formal research paper.
You have access to project context (narrative, codebase, workspace) and a curated literature list.

STRICT CITATION RULES:
- Only cite papers explicitly listed in the "Available Literature" section using [N] notation
- Every factual claim about the literature MUST have a [N] citation
- Never fabricate paper titles, authors, DOIs, or results
- If a claim cannot be supported by the provided papers, write "(citation needed)" rather than inventing one
- End the paper with a numbered References section listing every [N] cited

WRITING STANDARDS:
- Formal academic tone; active voice where natural ("We propose..." not "It is proposed...")
- Precise technical language; no buzzwords or marketing language
- Quantitative claims only where data exists in the project context
- Proper hedging: "results suggest" not "results prove"
- Clear topic sentences; paragraphs of 3-6 sentences
- Structure sections with logical flow: problem → gap → method → evidence → conclusion"""

_REVISION_SYSTEM = """You are a world-class academic writer revising a paper based on reviewer feedback.

Your task:
1. Read the reviewer's critique carefully
2. Address EVERY specific issue raised — do not skip any point
3. Preserve all content not criticised; improve only what the reviewer flagged
4. Keep all [N] citations intact; add new ones only from the Available Literature section
5. Do not introduce new content that was not mentioned in either the paper or the reviewer notes
6. Return the COMPLETE revised paper (all sections), not just the changed parts

End the paper with a complete numbered References section."""


def _build_draft_prompt(
    paper_type: str,
    title: str,
    target_venue: Optional[str],
    additional_instructions: Optional[str],
    context_block: str,
) -> str:
    """Build the user prompt for the initial draft generation."""
    venue_str = target_venue or "a suitable peer-reviewed venue"
    type_hint = _PAPER_TYPE_HINTS.get(paper_type, _PAPER_TYPE_HINTS["conference"])

    instructions = additional_instructions or "No additional instructions provided."

    return f"""Write a complete academic paper for the following project and target venue.

## Paper Requirements
Title: {title}
Type: {type_hint}
Target venue: {venue_str}
Additional instructions: {instructions}

## Project Context and Literature

{context_block}

---

Write the complete paper in Markdown now. Use ## for section headers.
Follow the structure appropriate for a {paper_type} paper.
Cite every literature claim using [N] notation from the Available Literature section.
End with a numbered References section."""


def _build_revision_prompt(
    paper_content: str,
    review_critique: str,
    review_name: str,
    context_block: str,
) -> str:
    """Build the user prompt for a revision pass."""
    return f"""You are revising a paper based on reviewer feedback from the "{review_name}" review pass.

## Reviewer Critique
{review_critique}

## Current Paper (to be revised)
{paper_content}

## Available Literature (for any new citations needed)
{context_block}

---

Address all reviewer points above. Return the COMPLETE revised paper in Markdown.
Preserve the full structure. End with a numbered References section."""


# ---------------------------------------------------------------------------
# Score extraction helper
# ---------------------------------------------------------------------------

def _extract_score(review_text: str) -> int:
    """
    Extract the numeric score from the reviewer's output.

    Looks for "Score: N" pattern at or near the end of the text.
    Returns 0 if no score found.
    """
    # Search the entire text, last match wins (score is at the end by instruction)
    matches = re.findall(r"Score:\s*(\d+)", review_text, re.IGNORECASE)
    if matches:
        try:
            return min(10, max(1, int(matches[-1])))
        except ValueError:
            pass
    return 0


# ---------------------------------------------------------------------------
# Progress tracking helpers using BlogPost.tags
# ---------------------------------------------------------------------------

def _build_progress_tags(step: str, pass_number: int, total_passes: int) -> List[str]:
    """Return a tags list encoding current pipeline progress for frontend polling."""
    pct = int((pass_number / (total_passes + 1)) * 100)
    return [
        "paper",
        f"progress:{pct}",
        f"step:{step}",
        f"pass:{pass_number}/{total_passes}",
    ]


async def _update_progress(
    post_id: uuid.UUID,
    step: str,
    pass_number: int,
    total_passes: int,
    db: AsyncSession,
) -> None:
    """Update BlogPost.tags with pipeline progress so the frontend can poll."""
    tags = _build_progress_tags(step, pass_number, total_passes)
    await update_blog_post(
        post_id,
        BlogPostUpdate(tags=tags, change_note=None),
        db,
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def generate_paper(
    project_id: uuid.UUID,
    paper_type: str,
    title: str,
    target_venue: Optional[str],
    additional_instructions: Optional[str],
    db: AsyncSession,
) -> Dict:
    """
    Run the full paper generation pipeline with 5 review passes.

    Steps:
      1. Build context (narrative + repo + workspace + literature)
      2. Generate initial draft (cloud AI)
      3. Store draft as BlogPost (version 1)
      4. For each of 5 REVIEW_PASSES:
         a. Reviewer critiques the current version (cloud AI with reviewer system)
         b. Writer revises based on critique (cloud AI with writer system)
         c. Snapshot the revision as a new BlogPostVersion
      5. Generate BibTeX from the papers found during context build
      6. Mark BlogPost complete (tags updated)
      7. Return full result dict

    Returns:
        {
            blog_post_id: str,
            title: str,
            final_content: str,
            bibtex: str,
            versions: [
                {
                    version: int,
                    review_name: str,
                    score: int,
                    review_notes: str,
                    diff_stats: dict,
                }
            ],
            review_summary: str,
        }
    """
    cloud_ai = get_cloud_client()
    total_passes = len(REVIEW_PASSES)

    # 1. Build context
    logger.info("paper_service: building context for project %s", project_id)
    context_block, papers = await _build_paper_context(project_id, db)

    # 2. Generate initial draft
    logger.info("paper_service: generating initial draft — title: %s", title)
    draft_prompt = _build_draft_prompt(
        paper_type=paper_type,
        title=title,
        target_venue=target_venue,
        additional_instructions=additional_instructions,
        context_block=context_block,
    )

    try:
        initial_draft = await cloud_ai.complete(system=_WRITER_SYSTEM, user=draft_prompt)
    except Exception:
        logger.exception("paper_service: initial draft generation failed")
        raise

    # 3. Store draft as a BlogPost (initial version = draft)
    post = await create_blog_post(
        project_id=project_id,
        data=BlogPostCreate(
            title=title,
            content=initial_draft,
            status="draft",
            tags=_build_progress_tags("draft_complete", 1, total_passes),
        ),
        db=db,
    )
    post_id = post.id
    logger.info("paper_service: created BlogPost %s for paper '%s'", post_id, title)

    # Track all version metadata for the response
    version_records: List[Dict] = []
    current_content = initial_draft

    # 4. Five review + revision passes
    for pass_idx, review_pass in enumerate(REVIEW_PASSES, start=1):
        review_name = review_pass["name"]
        reviewer_system = review_pass["system"]

        logger.info(
            "paper_service: starting review pass %d/%d — %s (post %s)",
            pass_idx,
            total_passes,
            review_name,
            post_id,
        )

        # 4a. Reviewer critiques
        review_user_prompt = (
            f"Review the following academic paper for: {review_name}\n\n"
            f"## Paper\n{current_content}"
        )
        try:
            critique = await cloud_ai.complete(
                system=reviewer_system,
                user=review_user_prompt,
            )
        except Exception:
            logger.exception(
                "paper_service: reviewer call failed for pass %d (%s)", pass_idx, review_name
            )
            critique = f"[Review failed for pass: {review_name}]"

        score = _extract_score(critique)
        logger.info(
            "paper_service: pass %d (%s) — score %d/10", pass_idx, review_name, score
        )

        # 4b. Writer revises
        revision_prompt = _build_revision_prompt(
            paper_content=current_content,
            review_critique=critique,
            review_name=review_name,
            context_block=context_block,
        )
        try:
            revised_content = await cloud_ai.complete(
                system=_REVISION_SYSTEM,
                user=revision_prompt,
            )
        except Exception:
            logger.exception(
                "paper_service: revision call failed for pass %d (%s)", pass_idx, review_name
            )
            # If revision fails, keep current content so the pipeline continues
            revised_content = current_content

        # 4c. Compute diff stats before snapshotting
        diff_stats = compute_diff_stats(current_content, revised_content)

        # 4d. Snapshot revised version
        change_note = f"{review_name} (score: {score}/10)"
        await update_blog_post(
            post_id=post_id,
            data=BlogPostUpdate(
                content=revised_content,
                change_note=change_note,
                tags=_build_progress_tags(f"pass_{pass_idx}_complete", pass_idx + 1, total_passes),
            ),
            db=db,
        )

        version_records.append({
            "version": pass_idx + 1,  # version 1 is the initial draft
            "review_name": review_name,
            "score": score,
            "review_notes": critique,
            "diff_stats": diff_stats,
        })

        current_content = revised_content

    # 5. Generate BibTeX
    logger.info("paper_service: generating BibTeX for %d papers", len(papers))
    try:
        bibtex = await generate_bibtex_for_papers(papers) if papers else ""
    except Exception:
        logger.exception("paper_service: BibTeX generation failed")
        bibtex = ""

    # 6. Mark complete
    final_tags = ["paper", "progress:100", "step:complete"]
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=current_content,
            tags=final_tags,
            change_note="Pipeline complete",
        ),
        db=db,
    )

    # 7. Build review summary
    scores = [v["score"] for v in version_records if v["score"] > 0]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    review_summary = (
        f"Completed {total_passes} review passes. "
        f"Scores: "
        + ", ".join(
            f"{v['review_name']}: {v['score']}/10" for v in version_records
        )
        + f". Average: {avg_score}/10."
    )

    logger.info(
        "paper_service: pipeline complete for post %s. %s", post_id, review_summary
    )

    return {
        "blog_post_id": str(post_id),
        "title": title,
        "final_content": current_content,
        "bibtex": bibtex,
        "versions": version_records,
        "review_summary": review_summary,
    }


# ---------------------------------------------------------------------------
# Multi-project (portfolio) paper pipeline
# ---------------------------------------------------------------------------

async def _build_portfolio_paper_context(
    project_ids: List[uuid.UUID],
    db: AsyncSession,
) -> Tuple[str, List[dict]]:
    """
    Build a combined context block from multiple projects for a portfolio paper.

    Iterates over each project and assembles its narrative, repo context, and
    workspace summary into a labelled section. Literature search is performed
    on the aggregated keyword set so that the resulting papers list spans all
    projects. Returns (context_block: str, papers: List[dict]).
    """
    all_sections: List[str] = []
    all_papers: List[dict] = []
    all_keywords: List[str] = []

    for idx, project_id in enumerate(project_ids, start=1):
        project_sections: List[str] = []
        narrative_ctx: dict = {}

        # Fetch project name for labelling
        project_name = f"Project {idx}"
        try:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if project:
                project_name = project.name
        except Exception:
            logger.exception(
                "paper_service: failed to load project row for %s", project_id
            )

        # -- Narrative --
        try:
            narrative = await get_or_create(project_id, db)
            narrative_ctx = build_context_block(narrative)
            parts: List[str] = []
            if narrative_ctx.get("one_liner"):
                parts.append(f"One-liner: {narrative_ctx['one_liner']}")
            if narrative_ctx.get("target_audience"):
                parts.append(f"Target audience: {narrative_ctx['target_audience']}")
            if narrative_ctx.get("origin_story"):
                parts.append(f"Origin story / motivation: {narrative_ctx['origin_story']}")
            if narrative_ctx.get("preferred_angles"):
                parts.append(f"Research angles: {', '.join(narrative_ctx['preferred_angles'])}")
            if parts:
                project_sections.append("### Narrative\n" + "\n".join(parts))
        except Exception:
            logger.exception(
                "paper_service: failed to load narrative for project %s", project_id
            )

        # -- GitHub repo context --
        try:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if project and project.github_repo:
                repo_ctx = await get_generation_context(project.github_repo, is_private=False)
                if repo_ctx and repo_ctx.strip():
                    if len(repo_ctx) > 6000:
                        repo_ctx = repo_ctx[:6000] + "\n\n[... truncated ...]"
                    project_sections.append(
                        f"### Repository Context (architecture/methods)\n{repo_ctx}"
                    )
        except Exception:
            logger.exception(
                "paper_service: failed to load repo context for project %s", project_id
            )

        # -- Workspace snapshot --
        try:
            snapshot = await get_latest_snapshot(project_id, db)
            if snapshot:
                ws_parts = [snapshot.summary]
                if snapshot.git_branch:
                    ws_parts.append(f"Current branch: {snapshot.git_branch}")
                project_sections.append(
                    "### Local Workspace\n" + "\n".join(ws_parts)
                )
        except Exception:
            logger.exception(
                "paper_service: failed to load workspace for project %s", project_id
            )

        if project_sections:
            all_sections.append(
                f"## Project: {project_name}\n\n" + "\n\n".join(project_sections)
            )

        # Accumulate keywords for the combined literature search
        if narrative_ctx.get("one_liner"):
            all_keywords.append(narrative_ctx["one_liner"])
        if narrative_ctx.get("origin_story"):
            first_sent = narrative_ctx["origin_story"].split(".")[0].strip()
            if first_sent and len(first_sent) > 10:
                all_keywords.append(first_sent[:120])
        for angle in (narrative_ctx.get("preferred_angles") or [])[:1]:
            if angle:
                all_keywords.append(str(angle))

    # -- Combined literature search --
    try:
        if all_keywords:
            # Deduplicate while preserving order (Python 3.9-compatible)
            seen: set = set()
            unique_kw: List[str] = []
            for kw in all_keywords:
                if kw not in seen:
                    seen.add(kw)
                    unique_kw.append(kw)
            all_papers = await find_related_work(unique_kw[:6], limit=25)
            if all_papers:
                all_sections.append(format_papers_for_prompt(all_papers))
    except Exception:
        logger.exception(
            "paper_service: Semantic Scholar search failed for portfolio paper"
        )

    return "\n\n".join(all_sections), all_papers


async def generate_portfolio_paper(
    project_ids: List[uuid.UUID],
    paper_type: str,
    title: str,
    target_venue: Optional[str],
    additional_instructions: Optional[str],
    db: AsyncSession,
) -> Dict:
    """
    Generate a paper covering multiple projects (e.g. a survey paper,
    portfolio technical report, or multi-system comparison paper).

    Same 5-round review pipeline as single-project papers, but context is
    assembled from ALL specified projects, following the pattern used by
    generate_portfolio_draft() in ai_generation.py.

    The resulting BlogPost is stored under the first project in the list.

    Returns the same structure as generate_paper().
    """
    cloud_ai = get_cloud_client()
    total_passes = len(REVIEW_PASSES)
    first_project_id = project_ids[0]

    # 1. Build combined context
    logger.info(
        "paper_service: building multi-project context for %d projects", len(project_ids)
    )
    context_block, papers = await _build_portfolio_paper_context(project_ids, db)

    # 2. Generate initial draft
    logger.info("paper_service: generating portfolio paper draft — title: %s", title)
    draft_prompt = _build_draft_prompt(
        paper_type=paper_type,
        title=title,
        target_venue=target_venue,
        additional_instructions=additional_instructions,
        context_block=context_block,
    )

    try:
        initial_draft = await cloud_ai.complete(system=_WRITER_SYSTEM, user=draft_prompt)
    except Exception:
        logger.exception("paper_service: portfolio paper initial draft generation failed")
        raise

    # 3. Store draft as a BlogPost under the first project
    post = await create_blog_post(
        project_id=first_project_id,
        data=BlogPostCreate(
            title=title,
            content=initial_draft,
            status="draft",
            tags=_build_progress_tags("draft_complete", 1, total_passes),
        ),
        db=db,
    )
    post_id = post.id
    logger.info(
        "paper_service: created BlogPost %s for portfolio paper '%s'", post_id, title
    )

    version_records: List[Dict] = []
    current_content = initial_draft

    # 4. Five review + revision passes (identical to generate_paper)
    for pass_idx, review_pass in enumerate(REVIEW_PASSES, start=1):
        review_name = review_pass["name"]
        reviewer_system = review_pass["system"]

        logger.info(
            "paper_service: portfolio paper review pass %d/%d — %s (post %s)",
            pass_idx,
            total_passes,
            review_name,
            post_id,
        )

        review_user_prompt = (
            f"Review the following academic paper for: {review_name}\n\n"
            f"## Paper\n{current_content}"
        )
        try:
            critique = await cloud_ai.complete(
                system=reviewer_system,
                user=review_user_prompt,
            )
        except Exception:
            logger.exception(
                "paper_service: reviewer call failed for portfolio pass %d (%s)",
                pass_idx,
                review_name,
            )
            critique = f"[Review failed for pass: {review_name}]"

        score = _extract_score(critique)

        revision_prompt = _build_revision_prompt(
            paper_content=current_content,
            review_critique=critique,
            review_name=review_name,
            context_block=context_block,
        )
        try:
            revised_content = await cloud_ai.complete(
                system=_REVISION_SYSTEM,
                user=revision_prompt,
            )
        except Exception:
            logger.exception(
                "paper_service: revision call failed for portfolio pass %d (%s)",
                pass_idx,
                review_name,
            )
            revised_content = current_content

        diff_stats = compute_diff_stats(current_content, revised_content)

        change_note = f"{review_name} (score: {score}/10)"
        await update_blog_post(
            post_id=post_id,
            data=BlogPostUpdate(
                content=revised_content,
                change_note=change_note,
                tags=_build_progress_tags(f"pass_{pass_idx}_complete", pass_idx + 1, total_passes),
            ),
            db=db,
        )

        version_records.append({
            "version": pass_idx + 1,
            "review_name": review_name,
            "score": score,
            "review_notes": critique,
            "diff_stats": diff_stats,
        })

        current_content = revised_content

    # 5. Generate BibTeX
    logger.info("paper_service: generating BibTeX for portfolio paper (%d papers)", len(papers))
    try:
        bibtex = await generate_bibtex_for_papers(papers) if papers else ""
    except Exception:
        logger.exception("paper_service: BibTeX generation failed for portfolio paper")
        bibtex = ""

    # 6. Mark complete
    final_tags = ["paper", "portfolio", "progress:100", "step:complete"]
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=current_content,
            tags=final_tags,
            change_note="Pipeline complete",
        ),
        db=db,
    )

    # 7. Build review summary
    scores = [v["score"] for v in version_records if v["score"] > 0]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    review_summary = (
        f"Completed {total_passes} review passes. "
        f"Scores: "
        + ", ".join(
            f"{v['review_name']}: {v['score']}/10" for v in version_records
        )
        + f". Average: {avg_score}/10."
    )

    logger.info(
        "paper_service: portfolio pipeline complete for post %s. %s", post_id, review_summary
    )

    return {
        "blog_post_id": str(post_id),
        "title": title,
        "final_content": current_content,
        "bibtex": bibtex,
        "versions": version_records,
        "review_summary": review_summary,
    }


# ---------------------------------------------------------------------------
# LaTeX export
# ---------------------------------------------------------------------------

async def export_to_latex(
    markdown_content: str,
    bibtex: str,
    template: str = "arxiv",
) -> Tuple[str, str]:
    """
    Convert a Markdown paper to LaTeX.

    Attempts to use pandoc if it is installed on the system PATH.
    If pandoc is not available, falls back to a pure-Python minimal conversion
    so the feature always works regardless of server configuration.

    Args:
        markdown_content: The full paper in Markdown.
        bibtex: BibTeX entries for the references section.
        template: LaTeX template style — "arxiv", "ieee", or "acm".

    Returns:
        (latex_content, bibtex_content) tuple.
    """
    # Try pandoc first
    try:
        latex = await _pandoc_convert(markdown_content, template)
        logger.info("export_to_latex: pandoc conversion succeeded (template: %s)", template)
        return latex, bibtex
    except FileNotFoundError:
        logger.info("export_to_latex: pandoc not found, using Python fallback")
    except Exception:
        logger.exception("export_to_latex: pandoc failed unexpectedly, using Python fallback")

    # Pure-Python fallback
    latex = _python_md_to_latex(markdown_content, template)
    return latex, bibtex


async def _pandoc_convert(markdown_content: str, template: str) -> str:
    """
    Run pandoc in a subprocess to convert Markdown to LaTeX.

    Raises FileNotFoundError if pandoc is not installed.
    Raises subprocess.CalledProcessError on conversion failure.
    """
    import asyncio

    # Map our template names to pandoc options
    template_args: List[str] = []
    if template == "ieee":
        template_args = ["--template", "ieee"]
    elif template == "acm":
        template_args = ["--template", "acm-sigconf"]
    # "arxiv" uses pandoc's default article LaTeX template

    with tempfile.NamedTemporaryFile(
        suffix=".md", mode="w", encoding="utf-8", delete=False
    ) as tmp_in:
        tmp_in.write(markdown_content)
        tmp_in_path = tmp_in.name

    try:
        cmd = ["pandoc", tmp_in_path, "-f", "markdown", "-t", "latex", "--standalone"] + template_args
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, output=stdout, stderr=stderr
            )
        return stdout.decode("utf-8")
    finally:
        import os
        try:
            os.unlink(tmp_in_path)
        except OSError:
            pass


def _python_md_to_latex(markdown_content: str, template: str) -> str:
    """
    Minimal Markdown → LaTeX converter using stdlib re.

    Handles:
    - ## H2 → \\section{}, ### H3 → \\subsection{}, #### H4 → \\subsubsection{}
    - **bold** → \\textbf{}, *italic* → \\textit{}
    - `code` → \\texttt{}
    - [N] citations → \\cite{refN}
    - References section → BibTeX placeholder comment
    - Blank lines → paragraph breaks (\\par)

    This is a best-effort conversion; complex tables and figures are passed through
    as verbatim comments so no content is silently dropped.
    """
    document_class: str
    packages: str

    if template == "ieee":
        document_class = "\\documentclass[conference]{IEEEtran}"
        packages = (
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath,amssymb,amsfonts}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}"
        )
    elif template == "acm":
        document_class = "\\documentclass[sigconf]{acmart}"
        packages = (
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath}\n"
            "\\usepackage{hyperref}"
        )
    else:  # arxiv / default
        document_class = "\\documentclass[12pt]{article}"
        packages = (
            "\\usepackage[margin=1in]{geometry}\n"
            "\\usepackage{cite}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage{hyperref}\n"
            "\\usepackage{setspace}\n"
            "\\doublespacing"
        )

    body_lines: List[str] = []
    lines = markdown_content.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]

        # Section headers
        if line.startswith("#### "):
            content = _escape_latex(line[5:].strip())
            body_lines.append(f"\\subsubsection{{{content}}}")
        elif line.startswith("### "):
            content = _escape_latex(line[4:].strip())
            body_lines.append(f"\\subsection{{{content}}}")
        elif line.startswith("## "):
            content = _escape_latex(line[3:].strip())
            # References section → use thebibliography
            if re.match(r"references?\s*$", content, re.IGNORECASE):
                body_lines.append(
                    "% Bibliography — insert your .bib file reference here\n"
                    "\\bibliographystyle{plain}\n"
                    "\\bibliography{references}"
                )
                i += 1
                continue
            body_lines.append(f"\\section{{{content}}}")
        elif line.startswith("# "):
            # Top-level H1 → title (only the first one)
            content = _escape_latex(line[2:].strip())
            body_lines.append(f"\\title{{{content}}}\n\\maketitle")
        elif line.strip() == "":
            body_lines.append("")  # paragraph break preserved
        else:
            body_lines.append(_convert_inline(line))

        i += 1

    body = "\n".join(body_lines)

    return (
        f"{document_class}\n"
        f"{packages}\n\n"
        f"\\begin{{document}}\n\n"
        f"{body}\n\n"
        f"\\end{{document}}\n"
    )


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in plain text."""
    # Order matters — backslash must come first
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _convert_inline(text: str) -> str:
    """
    Convert Markdown inline formatting to LaTeX.

    Handles **bold**, *italic*, `code`, and [N] citation references.
    Does not escape all LaTeX special chars — this is intentional for
    content that may already contain partial LaTeX from the AI writer.
    """
    # [N] citations → \cite{refN}
    text = re.sub(r"\[(\d+)\]", lambda m: f"\\cite{{ref{m.group(1)}}}", text)
    # **bold**
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"\\textbf{{{m.group(1)}}}", text)
    # *italic* (single asterisk, not already consumed by bold)
    text = re.sub(r"\*(.+?)\*", lambda m: f"\\textit{{{m.group(1)}}}", text)
    # `code`
    text = re.sub(r"`(.+?)`", lambda m: f"\\texttt{{{m.group(1)}}}", text)
    return text
