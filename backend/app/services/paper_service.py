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
import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import BlogPost, BlogPostVersion
from app.models.project import Project
from app.schemas.blog import BlogPostCreate, BlogPostUpdate
from app.services.ai_client import get_cloud_client, get_local_client, get_paper_reviewer_client
from app.services.egress_recorder import EgressRecorder
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


def _get_paper_reviewer():
    """Get reviewer client — gated through get_paper_reviewer_client().

    Using a different model for review than for drafting/revision avoids the
    failure mode where a model cannot objectively critique its own output.
    Returns the OpenAI client when "openai" is in settings.paper_reviewer_providers;
    otherwise falls back to the configured cloud client transparently.
    """
    return get_paper_reviewer_client("openai")


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
# Paper type → venue hint mapping (sourced from domain config at runtime)
# ---------------------------------------------------------------------------


def _paper_type_hint(paper_type: str) -> str:
    """Look up the type hint for a paper_type, falling back to "conference"."""
    from app.services.domain_config import get_loader

    hints = get_loader().get_paper_type_hints()
    hint = hints.get(paper_type) or hints.get("conference")
    if hint is None:
        return ""
    return hint.hint


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

    # -- Project knowledge (decisions/claims/insights/hypotheses) --
    try:
        from app.services.knowledge_service import search_knowledge
        proj_result = await db.execute(select(Project).where(Project.id == project_id))
        proj = proj_result.scalar_one_or_none()
        owner_user_id = proj.user_id if proj else None
        if owner_user_id is not None:
            # Build a query from narrative one-liner + angles for relevance ranking
            query_parts: List[str] = []
            if narrative_ctx.get("one_liner"):
                query_parts.append(narrative_ctx["one_liner"])
            for angle in (narrative_ctx.get("preferred_angles") or [])[:3]:
                if angle:
                    query_parts.append(str(angle))
            kn_query = " ".join(query_parts) or "project knowledge"

            hits = await search_knowledge(
                user_id=owner_user_id, query=kn_query, db=db,
                project_id=project_id, limit=15,
                node_types=["claim", "insight", "hypothesis", "decision"],
            )
            if hits:
                k_lines = [
                    f"- [{h.node.node_type}] {h.node.title} — {h.node.content}"
                    for h in hits
                ]
                sections.append("## Project Knowledge (prior decisions / claims / insights)\n"
                                + "\n".join(k_lines))
    except Exception:
        logger.exception(
            "paper_service: knowledge enrichment failed for project %s (non-fatal)",
            project_id,
        )

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
    type_hint = _paper_type_hint(paper_type)

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
    cloud_ai = get_cloud_client()        # writer / revision
    reviewer_ai = _get_paper_reviewer()  # reviewer — OpenAI when available
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
        async with EgressRecorder(
            surface="paper",
            service="paper_service.generate_paper",
            provider=type(cloud_ai).__name__.lower().replace("client", ""),
            model=getattr(cloud_ai, "_model", None) or getattr(cloud_ai, "chat_model", None),
            user_id=None,
            project_id=project_id,
        ) as rec:
            rec.field("system_prompt", _WRITER_SYSTEM)
            rec.field("paper_body", draft_prompt)
            rec.field("venue", target_venue or "")
            rec.field("additional_instructions", additional_instructions or "")
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

    # 4. ADAPTIVE review pipeline
    #    Strategy: run each review pass. If score < 8, re-review+revise that same
    #    aspect up to MAX_RETRIES times before moving on. After all 5 passes, if
    #    any score is still < 8, do a final comprehensive re-review cycle.
    #    Goal: every section scores 8+ out of 10.
    MAX_RETRIES_PER_PASS = 2  # retry low-scoring passes up to 2 extra times
    MAX_TOTAL_ROUNDS = 12     # hard cap to prevent infinite loops
    TARGET_SCORE = 8
    version_num = 1
    total_rounds = 0
    pass_scores: Dict[str, int] = {}  # track best score per review aspect

    for pass_idx, review_pass in enumerate(REVIEW_PASSES, start=1):
        review_name = review_pass["name"]
        reviewer_system = review_pass["system"]
        retries = 0

        while retries <= MAX_RETRIES_PER_PASS and total_rounds < MAX_TOTAL_ROUNDS:
            total_rounds += 1
            version_num += 1
            attempt_label = f"{review_name}" if retries == 0 else f"{review_name} (retry {retries})"

            logger.info(
                "paper_service: review round %d — %s (post %s)",
                total_rounds, attempt_label, post_id,
            )

            # 4a. Reviewer critiques
            review_user_prompt = (
                f"Review the following academic paper for: {review_name}\n\n"
                f"Score strictly 1-10. Only score 8+ if the section is genuinely publication-ready.\n\n"
                f"## Paper\n{current_content}"
            )
            try:
                critique = await reviewer_ai.complete(
                    system=reviewer_system,
                    user=review_user_prompt,
                )
            except Exception:
                logger.exception("paper_service: reviewer failed for %s", attempt_label)
                critique = f"[Review failed for: {attempt_label}]"

            score = _extract_score(critique)
            pass_scores[review_name] = max(pass_scores.get(review_name, 0), score)
            logger.info("paper_service: %s — score %d/10", attempt_label, score)

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
                logger.exception("paper_service: revision failed for %s", attempt_label)
                revised_content = current_content

            # 4c. Diff + snapshot
            diff_stats = compute_diff_stats(current_content, revised_content)
            change_note = f"{attempt_label} (score: {score}/10)"
            await update_blog_post(
                post_id=post_id,
                data=BlogPostUpdate(
                    content=revised_content,
                    change_note=change_note,
                    tags=_build_progress_tags(
                        f"round_{total_rounds}_complete", total_rounds, MAX_TOTAL_ROUNDS
                    ),
                ),
                db=db,
            )

            changes_made = (
                f"{diff_stats['lines_added']} lines added, "
                f"{diff_stats['lines_removed']} removed "
                f"({diff_stats['similarity_pct']}% similar)"
            )
            version_records.append({
                "version": version_num,
                "review_name": attempt_label,
                "score": score,
                "review_notes": critique,
                "changes_made": changes_made,
                "diff_stats": diff_stats,
            })

            current_content = revised_content

            # If score meets target, move to next review aspect
            if score >= TARGET_SCORE:
                logger.info("paper_service: %s passed (score %d >= %d)", review_name, score, TARGET_SCORE)
                break

            retries += 1
            if retries > MAX_RETRIES_PER_PASS:
                logger.warning(
                    "paper_service: %s did not reach target after %d retries (best: %d)",
                    review_name, MAX_RETRIES_PER_PASS, pass_scores[review_name],
                )

    # 4e. Final comprehensive check — if any aspect scored below target,
    #     do one final holistic review+revision
    low_scores = {k: v for k, v in pass_scores.items() if v < TARGET_SCORE}
    if low_scores and total_rounds < MAX_TOTAL_ROUNDS:
        total_rounds += 1
        version_num += 1
        weak_areas = ", ".join(f"{k} ({v}/10)" for k, v in low_scores.items())
        logger.info("paper_service: final polish — weak areas: %s", weak_areas)

        final_review_prompt = (
            f"This paper has been through multiple review rounds but these areas "
            f"still scored below 8/10: {weak_areas}.\n\n"
            f"Do a final comprehensive review focusing on these weak areas. "
            f"Score each area 1-10.\n\n## Paper\n{current_content}"
        )
        try:
            final_critique = await reviewer_ai.complete(
                system="You are a senior academic reviewer doing a final quality gate. "
                       "The paper must score 8+ in every area to pass. Be specific about remaining issues.",
                user=final_review_prompt,
            )
            final_revision = await cloud_ai.complete(
                system=_REVISION_SYSTEM,
                user=_build_revision_prompt(current_content, final_critique, "Final Polish", context_block),
            )
            diff_stats = compute_diff_stats(current_content, final_revision)
            final_score = _extract_score(final_critique)

            await update_blog_post(
                post_id=post_id,
                data=BlogPostUpdate(
                    content=final_revision,
                    change_note=f"Final Polish (score: {final_score}/10)",
                    tags=_build_progress_tags("final_polish", total_rounds, MAX_TOTAL_ROUNDS),
                ),
                db=db,
            )

            changes_made = (
                f"{diff_stats['lines_added']} lines added, "
                f"{diff_stats['lines_removed']} removed "
                f"({diff_stats['similarity_pct']}% similar)"
            )
            version_records.append({
                "version": version_num,
                "review_name": "Final Polish",
                "score": final_score,
                "review_notes": final_critique,
                "changes_made": changes_made,
                "diff_stats": diff_stats,
            })
            current_content = final_revision
        except Exception:
            logger.exception("paper_service: final polish failed")

    # Log final scores
    logger.info("paper_service: pipeline complete — scores: %s | total rounds: %d",
                pass_scores, total_rounds)

    # 5. Generate BibTeX
    logger.info("paper_service: generating BibTeX for %d papers", len(papers))
    try:
        bibtex = await generate_bibtex_for_papers(papers) if papers else ""
    except Exception:
        logger.exception("paper_service: BibTeX generation failed")
        bibtex = ""

    # 5b. Generate LaTeX inline so the response includes it without a separate call
    try:
        latex_content, _ = await export_to_latex(current_content, bibtex)
        logger.info("paper_service: inline LaTeX export succeeded")
    except Exception:
        logger.exception("paper_service: inline LaTeX export failed")
        latex_content = None

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

    # 8. Attach per-version content from DB for diff view
    version_chain = await get_version_chain(post_id, db)
    version_content_map = {v.version: v.content for v in version_chain}
    for rec in version_records:
        rec["content"] = version_content_map.get(rec["version"])

    return {
        "blog_post_id": str(post_id),
        "title": title,
        "final_content": current_content,
        "bibtex": bibtex,
        "latex": latex_content,
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

    Same adaptive review pipeline as single-project papers, but context is
    assembled from ALL specified projects, following the pattern used by
    generate_portfolio_draft() in ai_generation.py.

    The resulting BlogPost is stored under the first project in the list.

    Returns the same structure as generate_paper().
    """
    cloud_ai = get_cloud_client()        # writer / revision
    reviewer_ai = _get_paper_reviewer()  # reviewer — OpenAI when available
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
        async with EgressRecorder(
            surface="paper",
            service="paper_service.generate_portfolio_paper",
            provider=type(cloud_ai).__name__.lower().replace("client", ""),
            model=getattr(cloud_ai, "_model", None) or getattr(cloud_ai, "chat_model", None),
            user_id=None,
            project_id=first_project_id,
        ) as rec:
            rec.field("system_prompt", _WRITER_SYSTEM)
            rec.field("paper_body", draft_prompt)
            rec.field("venue", target_venue or "")
            rec.field("additional_instructions", additional_instructions or "")
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

    # 4. ADAPTIVE review pipeline (same as generate_paper)
    #    Each aspect retried until score >= 8, then final polish if needed.
    MAX_RETRIES_PER_PASS = 2
    MAX_TOTAL_ROUNDS = 12
    TARGET_SCORE = 8
    version_num = 1
    total_rounds = 0
    pass_scores: Dict[str, int] = {}

    for pass_idx, review_pass in enumerate(REVIEW_PASSES, start=1):
        review_name = review_pass["name"]
        reviewer_system = review_pass["system"]
        retries = 0

        while retries <= MAX_RETRIES_PER_PASS and total_rounds < MAX_TOTAL_ROUNDS:
            total_rounds += 1
            version_num += 1
            attempt_label = f"{review_name}" if retries == 0 else f"{review_name} (retry {retries})"

            logger.info("paper_service: portfolio round %d — %s (post %s)", total_rounds, attempt_label, post_id)

            review_user_prompt = (
                f"Review the following academic paper for: {review_name}\n\n"
                f"Score strictly 1-10. Only score 8+ if the section is genuinely publication-ready.\n\n"
                f"## Paper\n{current_content}"
            )
            try:
                critique = await reviewer_ai.complete(system=reviewer_system, user=review_user_prompt)
            except Exception:
                logger.exception("paper_service: portfolio reviewer failed for %s", attempt_label)
                critique = f"[Review failed for: {attempt_label}]"

            score = _extract_score(critique)
            pass_scores[review_name] = max(pass_scores.get(review_name, 0), score)

            revision_prompt = _build_revision_prompt(current_content, critique, review_name, context_block)
            try:
                revised_content = await cloud_ai.complete(system=_REVISION_SYSTEM, user=revision_prompt)
            except Exception:
                logger.exception("paper_service: portfolio revision failed for %s", attempt_label)
                revised_content = current_content

            diff_stats = compute_diff_stats(current_content, revised_content)
            change_note = f"{attempt_label} (score: {score}/10)"
            await update_blog_post(
                post_id=post_id,
                data=BlogPostUpdate(
                    content=revised_content,
                    change_note=change_note,
                    tags=_build_progress_tags(f"round_{total_rounds}_complete", total_rounds, MAX_TOTAL_ROUNDS),
                ),
                db=db,
            )

            changes_made = (
                f"{diff_stats['lines_added']} lines added, "
                f"{diff_stats['lines_removed']} removed "
                f"({diff_stats['similarity_pct']}% similar)"
            )
            version_records.append({
                "version": version_num,
                "review_name": attempt_label,
                "score": score,
                "review_notes": critique,
                "changes_made": changes_made,
                "diff_stats": diff_stats,
            })
            current_content = revised_content

            if score >= TARGET_SCORE:
                break
            retries += 1

    # Final polish for weak areas
    low_scores = {k: v for k, v in pass_scores.items() if v < TARGET_SCORE}
    if low_scores and total_rounds < MAX_TOTAL_ROUNDS:
        total_rounds += 1
        version_num += 1
        weak_areas = ", ".join(f"{k} ({v}/10)" for k, v in low_scores.items())
        logger.info("paper_service: portfolio final polish — weak: %s", weak_areas)
        try:
            final_critique = await reviewer_ai.complete(
                system="You are a senior academic reviewer doing a final quality gate. Score 8+ only if publication-ready.",
                user=f"Weak areas: {weak_areas}.\n\n## Paper\n{current_content}",
            )
            final_revision = await cloud_ai.complete(
                system=_REVISION_SYSTEM,
                user=_build_revision_prompt(current_content, final_critique, "Final Polish", context_block),
            )
            diff_stats = compute_diff_stats(current_content, final_revision)
            final_score = _extract_score(final_critique)
            await update_blog_post(
                post_id=post_id,
                data=BlogPostUpdate(content=final_revision, change_note=f"Final Polish (score: {final_score}/10)"),
                db=db,
            )
            version_records.append({
                "version": version_num,
                "review_name": "Final Polish",
                "score": final_score,
                "review_notes": final_critique,
                "changes_made": f"{diff_stats['lines_added']} added, {diff_stats['lines_removed']} removed",
                "diff_stats": diff_stats,
            })
            current_content = final_revision
        except Exception:
            logger.exception("paper_service: portfolio final polish failed")

    logger.info("paper_service: portfolio pipeline complete — scores: %s | rounds: %d", pass_scores, total_rounds)

    # 5. Generate BibTeX
    logger.info("paper_service: generating BibTeX for portfolio paper (%d papers)", len(papers))
    try:
        bibtex = await generate_bibtex_for_papers(papers) if papers else ""
    except Exception:
        logger.exception("paper_service: BibTeX generation failed for portfolio paper")
        bibtex = ""

    # 5b. Generate LaTeX inline so the response includes it without a separate call
    try:
        latex_content, _ = await export_to_latex(current_content, bibtex)
        logger.info("paper_service: inline LaTeX export succeeded for portfolio paper")
    except Exception:
        logger.exception("paper_service: inline LaTeX export failed for portfolio paper")
        latex_content = None

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

    # Attach per-version content from DB for diff view
    version_chain = await get_version_chain(post_id, db)
    version_content_map = {v.version: v.content for v in version_chain}
    for rec in version_records:
        rec["content"] = version_content_map.get(rec["version"])

    return {
        "blog_post_id": str(post_id),
        "title": title,
        "final_content": current_content,
        "bibtex": bibtex,
        "latex": latex_content,
        "versions": version_records,
        "review_summary": review_summary,
    }



# LaTeX export and PDF compilation have been extracted to latex_service.py.
# Re-export here for backward compatibility with existing imports.
from app.services.latex_service import compile_latex_to_pdf, export_to_latex  # noqa: F401


# ---------------------------------------------------------------------------
# Title suggestion
# ---------------------------------------------------------------------------

async def generate_paper_titles(
    project_id: uuid.UUID,
    paper_type: str,
    target_venue: Optional[str],
    db: AsyncSession,
    count: int = 5,
) -> List[Dict]:
    """
    Generate compelling paper title suggestions by:
    1. Loading project context (narrative, repo, workspace)
    2. Searching Semantic Scholar for top-cited papers in the field
    3. Analyzing title patterns from successful papers
    4. Generating titles in five distinct academic styles

    Returns a list of dicts with keys: title, style, rationale.
    Styles: descriptive | question | method-result | provocative | systematic
    """
    ai = get_cloud_client()

    # -- Load project context (narrative only — fast path, no full repo needed) --
    narrative_ctx: dict = {}
    narrative_summary = ""
    try:
        narrative = await get_or_create(project_id, db)
        narrative_ctx = build_context_block(narrative)
        parts: List[str] = []
        if narrative_ctx.get("one_liner"):
            parts.append(f"One-liner: {narrative_ctx['one_liner']}")
        if narrative_ctx.get("origin_story"):
            parts.append(f"Origin story: {narrative_ctx['origin_story']}")
        if narrative_ctx.get("target_audience"):
            parts.append(f"Target audience: {narrative_ctx['target_audience']}")
        if narrative_ctx.get("preferred_angles"):
            parts.append(f"Research angles: {', '.join(narrative_ctx['preferred_angles'])}")
        narrative_summary = "\n".join(parts)
    except Exception:
        logger.exception("generate_paper_titles: failed to load narrative for project %s", project_id)

    # -- Fetch top-cited related papers to learn title patterns --
    related_papers: List[dict] = []
    try:
        keywords: List[str] = []
        if narrative_ctx.get("one_liner"):
            keywords.append(narrative_ctx["one_liner"])
        for angle in (narrative_ctx.get("preferred_angles") or [])[:2]:
            if angle:
                keywords.append(str(angle))
        if keywords:
            # Sort by citation count to get the most prominent papers
            raw = await find_related_work(keywords, limit=15)
            related_papers = sorted(
                raw,
                key=lambda p: p.get("citationCount") or 0,
                reverse=True,
            )[:10]
    except Exception:
        logger.exception("generate_paper_titles: Semantic Scholar search failed")

    # Build a compact list of example titles from high-citation papers
    example_titles = "\n".join(
        f"- {p['title']} ({p.get('citationCount', 0)} citations)"
        for p in related_papers
        if p.get("title")
    )

    venue_str = target_venue or "a suitable peer-reviewed venue"
    type_hint = _paper_type_hint(paper_type)

    system = (
        "You are an expert academic title writer who understands what makes conference and "
        "journal paper titles compelling, memorable, and citation-worthy. "
        "You analyse patterns from real successful papers and apply them to new work."
    )

    user = (
        f"## Project Information\n{narrative_summary}\n\n"
        f"## Paper Type\n{type_hint}\n\n"
        f"## Target Venue\n{venue_str}\n\n"
        + (
            f"## Top-cited Related Papers (title patterns to learn from)\n{example_titles}\n\n"
            if example_titles else ""
        )
        + "## Task\n"
        "Analyse the title patterns from the related papers above (colon usage, question format, "
        "method naming, acronyms, result highlighting). Then generate EXACTLY 5 paper titles for "
        "this project, one in each of these academic styles:\n\n"
        "1. **descriptive** — States method/system name and domain clearly. "
        'Example: "HAVEN: A Value Exchange Protocol for Patient-Controlled Health Data"\n'
        "2. **question** — Poses the core research question. "
        'Example: "Can Patients Control Their Health Data? A Protocol Approach"\n'
        "3. **method-result** — Names the technique and what it achieves. "
        'Example: "Patient-Controlled Health Data Governance Through Programmable Consent"\n'
        "4. **provocative** — Bold, attention-grabbing claim. "
        'Example: "Health Data Belongs to Patients: A Protocol for Making It Real"\n'
        "5. **systematic** — Signals a rigorous, survey-style contribution. "
        'Example: "A Systematic Framework for Patient-Centered Health Data Exchange"\n\n'
        "For each title output EXACTLY this JSON object on its own line (no markdown fences):\n"
        '{"style": "<style>", "title": "<title>", "rationale": "<one sentence why this works>"}\n\n'
        "Output ONLY 5 JSON objects, one per line. No extra text."
    )

    try:
        async with EgressRecorder(
            surface="paper",
            service="paper_service.generate_paper_titles",
            provider=type(ai).__name__.lower().replace("client", ""),
            model=getattr(ai, "_model", None) or getattr(ai, "chat_model", None),
            user_id=None,
            project_id=project_id,
        ) as rec:
            rec.field("system_prompt", system)
            rec.field("paper_body", narrative_summary)
            rec.field("venue", target_venue or "")
            rec.field("additional_instructions", "")
            raw = await ai.complete(system=system, user=user)
    except Exception:
        logger.exception("generate_paper_titles: AI call failed")
        return []

    # Parse JSON objects from the response (one per line)
    import json as _json

    results: List[Dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip accidental markdown fences
        if line.startswith("```"):
            continue
        try:
            obj = _json.loads(line)
            if all(k in obj for k in ("style", "title", "rationale")):
                results.append({
                    "title": str(obj["title"]).strip(),
                    "style": str(obj["style"]).strip().lower(),
                    "rationale": str(obj["rationale"]).strip(),
                })
        except (_json.JSONDecodeError, TypeError, KeyError):
            logger.debug("generate_paper_titles: skipping non-JSON line: %s", line[:80])

    if not results:
        logger.warning(
            "generate_paper_titles: could not parse any JSON from AI response. "
            "Raw (first 300 chars): %s",
            raw[:300],
        )

    return results[:count]


async def get_paper_context(
    project_id: uuid.UUID,
    db: AsyncSession,
) -> Tuple[str, List[dict]]:
    """Public wrapper for the internal context builder used by the router endpoints."""
    return await _build_paper_context(project_id, db)
