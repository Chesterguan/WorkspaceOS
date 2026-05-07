"""
Paper Pipeline v2: multi-agent section-by-section generation with backtracking.

Pipeline phases:
  1. PLAN   — gemini_planner creates outline with page budgets per section
  2. DRAFT  — gemini_writer drafts each section; openai_critic reviews each;
               backtracking when upstream issues are found
  3. MERGE + COHERENCE — gemini_editor assembles sections, smooths transitions,
               condenses if over budget
  4. FINALIZE — generate BibTeX, LaTeX export

Also provides edit_paper() for post-generation editing (condense, section edit,
free-form instruction).
"""
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blog import BlogPost, BlogPostVersion
from app.schemas.blog import BlogPostCreate, BlogPostUpdate
from app.services.agents import AgentLog, NamedAgent, create_pipeline_agents, extract_json
from app.services.paper_reviewers import (
    run_review_roundtable,
    build_revision_brief,
    MIN_SCORE_FOR_PASS,
    MAX_ROUNDTABLE_ROUNDS,
)
from app.services.blog_service import create_blog_post, update_blog_post
from app.services.latex_service import export_to_latex
from app.services.paper_service import _build_paper_context
from app.services.scholar_service import generate_bibtex_for_papers
from app.services.venue_service import VenueGuidelines, resolve_venue
from app.utils.diff_utils import compute_diff_stats

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_SECTION_RETRIES = 2
MAX_BACKTRACK_DEPTH = 2
TARGET_SCORE = 8


def _safe_score(value: Any) -> int:
    """Safely convert an AI-returned score to int. Returns 0 on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _count_top_level_sections(text: str) -> int:
    """Count '## N.' or '### N.' headings — used to detect section drops."""
    import re
    return len(re.findall(r"^#{2,3}\s+\d+\.", text, flags=re.MULTILINE))


def _extract_headings(text: str) -> str:
    """Pull '##/### N. Title' lines into a bullet list for the planner prompt."""
    import re
    headings = re.findall(r"^#{2,3}\s+(.+)$", text, flags=re.MULTILINE)
    return "\n".join(f"- {h.strip()}" for h in headings) or "(no headings detected)"

# ---------------------------------------------------------------------------
# Prompt constants — system prompts for each agent role
# ---------------------------------------------------------------------------

_PLANNER_SYSTEM = (
    "You are a research paper planner. Your job is to create a structured outline "
    "with page budgets for each section.\n\n"
    "Given:\n"
    "- Paper title, type, and target venue (with constraints if available)\n"
    "- Project context (narrative, repo, workspace)\n"
    "- Available literature\n\n"
    "Output ONLY a JSON object (no markdown fences, no prose):\n"
    "{\n"
    '  "sections": [\n'
    '    {"number": "1", "title": "Introduction", "pages": 1.5, '
    '"depends_on": [], "key_points": ["...", "..."]},\n'
    '    {"number": "2", "title": "Background", "pages": 1.5, '
    '"depends_on": ["1"], "key_points": ["...", "..."]},\n'
    "    ...\n"
    "  ],\n"
    '  "total_pages": 8\n'
    "}\n\n"
    "Rules:\n"
    "- If venue has a page limit, total_pages MUST equal that limit.\n"
    "- Each section must have a page budget that sums to total_pages.\n"
    "- Section numbers are strings: '1', '2', '3', etc.\n"
    "- depends_on lists section numbers that must be written first.\n"
    "- key_points lists 2-4 bullet items the section should cover."
)

_PLANNER_BACKTRACK_SYSTEM = (
    "You are a research paper planner handling a cross-section issue flagged "
    "by a reviewer.\n\n"
    "Given:\n"
    "- The critic's upstream issue (which section needs fixing and why)\n"
    "- The current section being reviewed\n"
    "- All sections written so far\n\n"
    "Decide the best action and output ONLY a JSON object:\n"
    "{\n"
    '  "action": "revise_upstream" or "adjust_current",\n'
    '  "target_section": "2",\n'
    '  "instruction": "Add a formal definition of X in section 2 before it is used"\n'
    "}\n\n"
    "Choose 'revise_upstream' when the issue is a missing definition, notation, "
    "or concept that truly belongs in the earlier section.\n"
    "Choose 'adjust_current' when the current section can be self-contained "
    "with a brief inline clarification."
)

_PLANNER_INSERT_DECIDE_SYSTEM = (
    "You are a paper-editing dispatcher. Given a user instruction and the paper's "
    "section headings, decide whether the change is local to one section or truly global. "
    "Most insertion-style instructions ('add a paragraph about X', 'mention Y') are LOCAL — "
    "find the most appropriate existing section and route there. "
    "Only choose 'global' for cross-cutting concerns like length, tone, or paper-wide style."
)

_WRITER_SECTION_SYSTEM = (
    "You are an academic paper writer. Your job is to write ONE section of a "
    "research paper.\n\n"
    "Rules:\n"
    "- Write in formal academic style with precise technical language.\n"
    "- Use [N] citation markers (e.g. [1], [2]) for references.\n"
    "- Match the tone and terminology of prior sections (provided as context).\n"
    "- Stay within the page budget given in the instructions.\n"
    "- Include all key points listed in the section outline.\n"
    "- Output ONLY the section content (with its heading). No preamble or "
    "meta-commentary."
)

_WRITER_REVISE_SYSTEM = (
    "You are an academic paper writer revising a section based on reviewer "
    "feedback.\n\n"
    "Rules:\n"
    "- Address every issue raised by the reviewer.\n"
    "- Preserve the section's overall structure unless the reviewer explicitly "
    "asks for restructuring.\n"
    "- Keep the same citation markers and terminology as the original.\n"
    "- Stay within the page budget.\n"
    "- Output ONLY the revised section content (with its heading). No preamble."
)

_WRITER_FULL_REVISE_SYSTEM = (
    "You are an academic paper writer revising a complete multi-section paper "
    "based on roundtable reviewer feedback.\n\n"
    "Hard rules — NEVER violate:\n"
    "1. Return EVERY section that was in the input paper, in the SAME order.\n"
    "2. Do NOT drop, merge, or reorder sections. The Abstract MUST stay at the top, "
    "the References MUST stay at the bottom.\n"
    "3. Preserve every section heading exactly (including its number prefix).\n"
    "4. Preserve every [N] citation marker. Do not renumber citations.\n"
    "5. Preserve all figure/table captions and inline references to them.\n\n"
    "What to change:\n"
    "- Address every critical issue raised by the reviewers.\n"
    "- Address as many suggestions as fit within the existing section budgets.\n"
    "- Improve clarity, rigor, and consistency without restructuring.\n\n"
    "Output ONLY the complete revised paper. No preamble, no meta-commentary, "
    "no summary of what you changed. Begin with the very first heading."
)

_CRITIC_SECTION_SYSTEM = (
    "You are a senior academic reviewer. Review the given section in the context "
    "of ALL existing sections of the paper.\n\n"
    "Check for:\n"
    "1. Quality of this section (clarity, rigor, evidence) — score 1-10\n"
    "2. Consistency with other sections (terminology, notation, claims)\n"
    "3. Upstream dependencies — does this section reference anything not yet defined?\n"
    "4. Downstream impact — does this section introduce concepts that later "
    "sections need?\n\n"
    "Output ONLY a JSON object (no markdown fences, no prose):\n"
    "{\n"
    '  "score": 8,\n'
    '  "critique": "...",\n'
    '  "upstream_issues": [{"target_section": "2", "issue": "..."}],\n'
    '  "passed": true\n'
    "}\n\n"
    "Rules:\n"
    "- Score strictly 1-10. Only score 8+ if the section is genuinely "
    "publication-ready.\n"
    "- upstream_issues should be an empty list if none exist.\n"
    "- passed is true when score >= 8 AND no upstream issues."
)

_EDITOR_COHERENCE_SYSTEM = (
    "You are an academic editor performing a coherence pass on a complete paper.\n\n"
    "Hard rules — NEVER violate:\n"
    "1. Return EVERY section that was in the input paper, in the SAME order.\n"
    "2. Do NOT drop, merge, split, or reorder sections.\n"
    "3. Preserve every section heading exactly (including its number prefix).\n"
    "4. Preserve every [N] citation marker. Do not renumber citations.\n"
    "5. The Abstract stays at the top; References stay at the bottom.\n\n"
    "Your job — within those hard rules:\n"
    "1. Smooth transitions between sections.\n"
    "2. Normalize terminology and notation across sections.\n"
    "3. Fix internal inconsistencies (e.g., a claim in section 3 contradicting one in section 5).\n"
    "4. Tighten prose without dropping content.\n\n"
    "Output ONLY the complete polished paper. No preamble, no summary."
)

_EDITOR_CONDENSE_SYSTEM = (
    "You are a senior academic editor. Your job is to condense a research paper "
    "to fit within a target page limit.\n\n"
    "Rules:\n"
    "- Preserve all key contributions and claims.\n"
    "- Remove redundant examples, verbose transitions, and excessive background.\n"
    "- Merge short sections where appropriate.\n"
    "- Keep all citation markers intact.\n"
    "- Do NOT remove entire sections unless they are clearly appendix material "
    "and the page budget demands it.\n"
    "- Output the COMPLETE condensed paper. Do not summarize — output the "
    "full text."
)

# Default outline used when the planner returns nothing useful.
_DEFAULT_OUTLINE: List[Dict] = [
    {"number": "1", "title": "Introduction", "pages": 1.5,
     "depends_on": [], "key_points": ["Motivation", "Problem statement", "Contributions"]},
    {"number": "2", "title": "Background", "pages": 1.5,
     "depends_on": ["1"], "key_points": ["Related work", "Definitions", "Theoretical foundation"]},
    {"number": "3", "title": "Methodology", "pages": 2.0,
     "depends_on": ["2"], "key_points": ["Approach", "Design decisions", "Implementation"]},
    {"number": "4", "title": "Evaluation", "pages": 1.5,
     "depends_on": ["3"], "key_points": ["Experimental setup", "Results", "Analysis"]},
    {"number": "5", "title": "Discussion", "pages": 1.0,
     "depends_on": ["4"], "key_points": ["Implications", "Limitations", "Threats to validity"]},
    {"number": "6", "title": "Conclusion", "pages": 0.5,
     "depends_on": ["5"], "key_points": ["Summary", "Future work"]},
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _venue_block(venue: Optional[VenueGuidelines]) -> str:
    """Build a venue-constraints string for inclusion in prompts."""
    if venue is None or not venue.has_constraints():
        return ""
    parts: List[str] = [f"Target venue: {venue.venue_name}"]
    if venue.page_limit is not None:
        parts.append(f"Page limit: {venue.page_limit}")
    if venue.word_limit is not None:
        parts.append(f"Word limit: {venue.word_limit}")
    if venue.template:
        parts.append(f"Template: {venue.template}")
    if venue.anonymization:
        parts.append("Anonymization: required (double-blind)")
    if venue.topics:
        parts.append(f"Topics: {', '.join(venue.topics)}")
    return "\n".join(parts)


def _progress_tags(step: str, current: int, total: int) -> List[str]:
    """Return tags encoding current v2 pipeline progress for frontend polling."""
    pct = min(int((current / max(total, 1)) * 100), 99)
    return ["paper", "v2", f"progress:{pct}", f"step:{step}"]


def _estimate_pages(text: str) -> float:
    """Rough page estimate: ~300 words per page for academic text."""
    word_count = len(text.split())
    return round(word_count / 300, 1)


# ---------------------------------------------------------------------------
# Phase 1: PLAN
# ---------------------------------------------------------------------------

async def _phase_plan(
    planner: NamedAgent,
    title: str,
    paper_type: str,
    context_block: str,
    venue: Optional[VenueGuidelines],
) -> List[Dict]:
    """Ask the planner to produce an outline with page budgets per section.

    Falls back to _DEFAULT_OUTLINE if the planner returns nothing parseable.
    """
    venue_text = _venue_block(venue)
    page_target = ""
    if venue and venue.page_limit:
        page_target = f"\nThe paper MUST be exactly {venue.page_limit} pages."

    user_prompt = (
        f"Paper title: {title}\n"
        f"Paper type: {paper_type}\n"
        f"{venue_text}\n"
        f"{page_target}\n\n"
        f"## Project Context\n{context_block[:6000]}\n\n"
        "Produce the JSON outline now."
    )

    result = await planner.complete_json(
        system=_PLANNER_SYSTEM,
        user=user_prompt,
        action="plan_outline",
    )

    sections = result.get("sections", [])
    if not sections or not isinstance(sections, list):
        logger.warning("_phase_plan: planner returned no sections, using default outline")
        planner.log.add(
            "gemini_planner", "plan_fallback",
            "Planner output unusable; using default 6-section outline",
        )
        sections = list(_DEFAULT_OUTLINE)
        # Adjust default page budgets to venue limit if provided
        if venue and venue.page_limit:
            total_default = sum(s["pages"] for s in sections)
            ratio = venue.page_limit / total_default
            for s in sections:
                s["pages"] = round(s["pages"] * ratio, 1)

    return sections


# ---------------------------------------------------------------------------
# Phase 2: DRAFT (sequential with backtracking)
# ---------------------------------------------------------------------------

async def _phase_draft(
    agents: Dict[str, NamedAgent],
    sections: List[Dict],
    context_block: str,
    venue: Optional[VenueGuidelines],
) -> Dict[str, str]:
    """Draft each section sequentially with critic review and backtracking.

    Returns a dict mapping section number (str) to content (str).
    """
    writer = agents["gemini_writer"]
    critic = agents["openai_critic"]
    planner = agents["gemini_planner"]
    agent_log = writer.log

    written: Dict[str, str] = {}  # section number -> content
    venue_text = _venue_block(venue)

    for section in sections:
        sec_num = str(section["number"])
        sec_title = section.get("title", f"Section {sec_num}")
        sec_pages = section.get("pages", 1.5)
        sec_points = section.get("key_points", [])
        sec_label = f"{sec_num}. {sec_title}"

        # Build context: all previously written sections
        prior_text = "\n\n".join(
            f"### {k}. {_find_section_title(sections, k)}\n{v}"
            for k, v in written.items()
        )

        # --- Writer drafts the section ---
        draft_user = (
            f"## Outline\n"
            f"Section: {sec_label}\n"
            f"Page budget: ~{sec_pages} pages (~{int(sec_pages * 300)} words)\n"
            f"Key points to cover: {', '.join(sec_points) if sec_points else 'see outline'}\n"
            f"{venue_text}\n\n"
            f"## Project Context (abbreviated)\n{context_block[:4000]}\n\n"
        )
        if prior_text:
            draft_user += f"## Previously Written Sections\n{prior_text}\n\n"
        draft_user += f"Write section '{sec_label}' now."

        section_content = await writer.complete(
            system=_WRITER_SECTION_SYSTEM,
            user=draft_user,
            action="draft_section",
            section=sec_label,
        )

        # --- Critic reviews ---
        retries = 0
        backtrack_count = 0

        while retries <= MAX_SECTION_RETRIES:
            review_context = prior_text + f"\n\n### {sec_label} (UNDER REVIEW)\n{section_content}"
            review_user = (
                f"Review the section '{sec_label}' in the context of the full paper so far.\n"
                f"{venue_text}\n\n"
                f"## Paper Sections\n{review_context}\n\n"
                "Output your JSON review now."
            )

            review_result = await critic.complete_json(
                system=_CRITIC_SECTION_SYSTEM,
                user=review_user,
                action="review_section",
                section=sec_label,
            )

            score = _safe_score(review_result.get("score", 0))
            critique = review_result.get("critique", "")
            upstream_issues = review_result.get("upstream_issues", [])
            passed = review_result.get("passed", score >= TARGET_SCORE)

            agent_log.add(
                "openai_critic", "review_section",
                f"Score {score}/10: {critique[:150]}",
                section=sec_label,
                score=score,
            )

            if passed and score >= TARGET_SCORE:
                break

            # --- Handle backtracking for upstream issues ---
            if upstream_issues and backtrack_count < MAX_BACKTRACK_DEPTH:
                for issue in upstream_issues[:1]:  # handle one upstream issue at a time
                    target_sec = str(issue.get("target_section", ""))
                    issue_text = issue.get("issue", "")

                    if target_sec not in written:
                        # Target section not yet written — skip backtrack
                        agent_log.add(
                            "gemini_planner", "backtrack_skip",
                            f"Target section {target_sec} not yet written; "
                            f"will address in current section",
                            section=sec_label,
                        )
                        continue

                    # Ask planner to decide action
                    bt_user = (
                        f"Critic flagged an upstream issue while reviewing '{sec_label}':\n"
                        f"Target section: {target_sec}\n"
                        f"Issue: {issue_text}\n\n"
                        f"Current sections written: {list(written.keys())}\n\n"
                        "Decide: revise_upstream or adjust_current?"
                    )
                    bt_decision = await planner.complete_json(
                        system=_PLANNER_BACKTRACK_SYSTEM,
                        user=bt_user,
                        action="backtrack_decision",
                        section=sec_label,
                    )

                    action = bt_decision.get("action", "adjust_current")
                    bt_instruction = bt_decision.get("instruction", issue_text)

                    if action == "revise_upstream" and target_sec in written:
                        # Revise the upstream section
                        target_title = _find_section_title(sections, target_sec)
                        target_label = f"{target_sec}. {target_title}"

                        revise_user = (
                            f"## Section to Revise\n{target_label}\n\n"
                            f"## Current Content\n{written[target_sec]}\n\n"
                            f"## Reviewer Feedback\n{bt_instruction}\n\n"
                            "Revise this section to address the issue. "
                            "Output ONLY the revised section content."
                        )
                        revised_upstream = await writer.complete(
                            system=_WRITER_REVISE_SYSTEM,
                            user=revise_user,
                            action="revise_upstream",
                            section=target_label,
                        )
                        written[target_sec] = revised_upstream
                        agent_log.add(
                            "gemini_writer", "backtrack_revise",
                            f"Revised upstream section {target_label}: {bt_instruction[:100]}",
                            section=target_label,
                        )

                        # Rebuild prior_text after upstream revision
                        prior_text = "\n\n".join(
                            f"### {k}. {_find_section_title(sections, k)}\n{v}"
                            for k, v in written.items()
                        )
                        backtrack_count += 1
                    else:
                        # Adjust current section instead
                        agent_log.add(
                            "gemini_planner", "backtrack_adjust_current",
                            f"Adjusting current section instead: {bt_instruction[:100]}",
                            section=sec_label,
                        )

            # --- Revise current section based on critique ---
            retries += 1
            if retries > MAX_SECTION_RETRIES:
                agent_log.add(
                    "gemini_writer", "section_max_retries",
                    f"Section {sec_label} did not reach target after "
                    f"{MAX_SECTION_RETRIES} retries (best score: {score})",
                    section=sec_label,
                    score=score,
                )
                break

            revise_user = (
                f"## Section to Revise\n{sec_label}\n\n"
                f"## Current Content\n{section_content}\n\n"
                f"## Reviewer Feedback (score: {score}/10)\n{critique}\n\n"
            )
            if prior_text:
                revise_user += f"## Previously Written Sections\n{prior_text}\n\n"
            revise_user += "Revise this section to address all reviewer issues."

            section_content = await writer.complete(
                system=_WRITER_REVISE_SYSTEM,
                user=revise_user,
                action="revise_section",
                section=sec_label,
            )

        # Store the final version of this section
        written[sec_num] = section_content

    return written


def _find_section_title(sections: List[Dict], sec_num: str) -> str:
    """Look up a section title by number from the outline."""
    for s in sections:
        if str(s.get("number", "")) == str(sec_num):
            return s.get("title", f"Section {sec_num}")
    return f"Section {sec_num}"


# ---------------------------------------------------------------------------
# Phase 3: MERGE + COHERENCE
# ---------------------------------------------------------------------------

async def _phase_roundtable_review(
    agents: Dict[str, NamedAgent],
    sections: List[Dict],
    written_sections: Dict[str, str],
    venue: Optional[VenueGuidelines],
) -> Tuple[str, List[Dict]]:
    """Phase 3: Assemble, coherence pass, roundtable review, revision.

    Returns (final_paper_content, roundtable_reviews).
    """
    editor = agents["gemini_editor"]
    writer = agents["gemini_writer"]
    agent_log = editor.log
    venue_text = _venue_block(venue)

    # --- Step 1: Assemble sections ---
    assembled_parts: List[str] = []
    for section in sections:
        sec_num = str(section["number"])
        sec_title = section.get("title", f"Section {sec_num}")
        content = written_sections.get(sec_num, "")
        if content:
            assembled_parts.append(content)
        else:
            assembled_parts.append(f"## {sec_num}. {sec_title}\n\n[Section not generated]")

    assembled = "\n\n".join(assembled_parts)

    # --- Step 2: Coherence pass ---
    coherence_user = (
        f"## Full Paper\n{assembled}\n\n"
        f"{venue_text}\n\n"
        "Perform a coherence pass: smooth transitions, normalize terminology, "
        "fix inconsistencies. Output the COMPLETE paper."
    )
    paper = await editor.complete(
        system=_EDITOR_COHERENCE_SYSTEM,
        user=coherence_user,
        action="coherence_pass",
    )

    # --- Step 3: Condense if over budget ---
    if venue and venue.page_limit:
        estimated = _estimate_pages(paper)
        budget_threshold = venue.page_limit * 1.15
        if estimated > budget_threshold:
            agent_log.add(
                "gemini_editor", "condense_triggered",
                f"Paper is ~{estimated} pages, budget is {venue.page_limit}. Condensing.",
            )
            condense_user = (
                f"## Full Paper\n{paper}\n\n"
                f"Target: {venue.page_limit} pages (~{venue.page_limit * 300} words).\n"
                f"{venue_text}\n\n"
                "Condense the paper to fit. Output the COMPLETE paper."
            )
            paper = await editor.complete(
                system=_EDITOR_CONDENSE_SYSTEM,
                user=condense_user,
                action="condense_pass",
            )

    # --- Step 4: Roundtable review (up to MAX_ROUNDTABLE_ROUNDS) ---
    all_reviews: List[Dict] = []
    for round_num in range(1, MAX_ROUNDTABLE_ROUNDS + 1):
        agent_log.add(
            "system", "roundtable_start",
            f"Roundtable review round {round_num}/{MAX_ROUNDTABLE_ROUNDS}",
        )

        reviews = await run_review_roundtable(paper, venue_text, agent_log)
        all_reviews = reviews

        brief = build_revision_brief(reviews)
        min_score = min(r["score"] for r in reviews) if reviews else 0
        avg_score = sum(r["score"] for r in reviews) / len(reviews) if reviews else 0

        agent_log.add(
            "system", "roundtable_complete",
            f"Round {round_num}: avg {avg_score:.1f}/10, min {min_score}/10, "
            f"{sum(len(r.get('critical_issues', [])) for r in reviews)} critical issues",
        )

        # --- Step 5: Writer revises based on roundtable feedback ---
        revision_user = (
            f"## Paper to Revise\n\n{paper}\n\n"
            f"{brief}\n\n"
            f"{venue_text}\n\n"
            "Address ALL critical issues and as many suggestions as feasible. "
            "Return the COMPLETE revised paper."
        )
        paper = await writer.complete(
            system=_WRITER_FULL_REVISE_SYSTEM,
            user=revision_user,
            action="roundtable_revision",
            section=f"round_{round_num}",
        )

        if min_score >= MIN_SCORE_FOR_PASS:
            agent_log.add(
                "system", "roundtable_passed",
                f"All reviewers scored >= {MIN_SCORE_FOR_PASS}, skipping additional rounds",
            )
            break

    # --- Section-count guardrail: warn if revision dropped sections ---
    expected = len(sections)
    got = _count_top_level_sections(paper)
    if got < expected:
        agent_log.add(
            "system", "section_count_warning",
            f"Section count dropped: expected {expected}, got {got}. "
            "This indicates a revision step removed sections.",
        )

    return paper, all_reviews


# ---------------------------------------------------------------------------
# Phase 4: FINALIZE
# ---------------------------------------------------------------------------

async def _phase_finalize(papers: List[dict]) -> str:
    """Generate BibTeX from the literature papers found during context build.

    Returns the bibtex string (empty string if no papers or on failure).
    """
    if not papers:
        return ""
    try:
        bibtex = await generate_bibtex_for_papers(papers)
        return bibtex
    except Exception:
        logger.exception("_phase_finalize: BibTeX generation failed")
        return ""


# ---------------------------------------------------------------------------
# Main entry point: generate_paper_v2
# ---------------------------------------------------------------------------

async def generate_paper_v2(
    project_id: uuid.UUID,
    paper_type: str,
    title: str,
    target_venue: Optional[str],
    additional_instructions: Optional[str],
    db: AsyncSession,
) -> Dict:
    """Run the full v2 multi-agent paper generation pipeline.

    Returns a dict with: blog_post_id, title, final_content, bibtex, latex,
    versions, review_summary, agent_log, venue_guidelines.
    """
    agent_log = AgentLog()
    agents = create_pipeline_agents(agent_log)

    # Total steps for progress tracking (plan + N sections + merge + finalize)
    # We'll update as we learn section count.
    total_steps = 10  # initial estimate

    # --- Resolve venue ---
    venue: Optional[VenueGuidelines] = None
    if target_venue:
        try:
            venue = await resolve_venue(target_venue, db)
            agent_log.add(
                "system", "venue_resolved",
                f"Venue '{venue.venue_name}' resolved (source: {venue.source}, "
                f"page_limit: {venue.page_limit})",
            )
        except Exception:
            logger.exception("generate_paper_v2: venue resolution failed for '%s'", target_venue)

    # --- Build context ---
    logger.info("generate_paper_v2: building context for project %s", project_id)
    context_block, papers = await _build_paper_context(project_id, db)

    if additional_instructions:
        context_block += f"\n\n## Additional Instructions\n{additional_instructions}"

    # ---------------------------------------------------------------
    # Phase 1: PLAN
    # ---------------------------------------------------------------
    logger.info("generate_paper_v2: Phase 1 — PLAN")
    sections = await _phase_plan(
        agents["gemini_planner"], title, paper_type, context_block, venue,
    )
    total_steps = len(sections) + 3  # sections + plan + merge + finalize
    step_counter = 1

    # ---------------------------------------------------------------
    # Create BlogPost to track progress
    # ---------------------------------------------------------------
    post = await create_blog_post(
        project_id=project_id,
        data=BlogPostCreate(
            title=title,
            content="",
            status="draft",
            tags=_progress_tags("plan_complete", step_counter, total_steps),
        ),
        db=db,
    )
    post_id = post.id
    logger.info("generate_paper_v2: created BlogPost %s", post_id)

    # ---------------------------------------------------------------
    # Phase 2: DRAFT
    # ---------------------------------------------------------------
    logger.info("generate_paper_v2: Phase 2 — DRAFT (%d sections)", len(sections))
    written_sections = await _phase_draft(agents, sections, context_block, venue)

    # Update progress after each conceptual step
    step_counter += len(sections)
    partial_content = "\n\n".join(
        written_sections.get(str(s["number"]), "")
        for s in sections
        if written_sections.get(str(s["number"]))
    )
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=partial_content,
            tags=_progress_tags("draft_complete", step_counter, total_steps),
            change_note="All sections drafted",
        ),
        db=db,
    )

    # ---------------------------------------------------------------
    # Phase 3: MERGE + COHERENCE
    # ---------------------------------------------------------------
    logger.info("generate_paper_v2: Phase 3 — ROUNDTABLE REVIEW")
    step_counter += 1
    final_content, roundtable_reviews = await _phase_roundtable_review(
        agents, sections, written_sections, venue,
    )

    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=final_content,
            tags=_progress_tags("merge_complete", step_counter, total_steps),
            change_note="Coherence pass complete",
        ),
        db=db,
    )

    # ---------------------------------------------------------------
    # Phase 4: FINALIZE (BibTeX + LaTeX)
    # ---------------------------------------------------------------
    logger.info("generate_paper_v2: Phase 4 — FINALIZE")
    step_counter += 1
    bibtex = await _phase_finalize(papers)

    latex_content: Optional[str] = None
    template = "arxiv"
    if venue and venue.template:
        template = venue.template
    try:
        latex_content, _ = await export_to_latex(final_content, bibtex, template=template)
        logger.info("generate_paper_v2: LaTeX export succeeded (template: %s)", template)
    except Exception:
        logger.exception("generate_paper_v2: LaTeX export failed")

    # ---------------------------------------------------------------
    # Mark complete
    # ---------------------------------------------------------------
    final_tags = ["paper", "v2", "progress:100", "step:complete"]
    if venue:
        final_tags.append(f"venue:{venue.venue_name}")
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=final_content,
            tags=final_tags,
            change_note="Pipeline complete",
        ),
        db=db,
    )

    # ---------------------------------------------------------------
    # Build version_records from agent_log entries that have scores
    # ---------------------------------------------------------------
    version_records: List[Dict] = []
    scored_entries = [e for e in agent_log.entries if e.get("score") is not None]
    for idx, entry in enumerate(scored_entries, start=1):
        version_records.append({
            "version": idx,
            "review_name": f"{entry.get('section', 'full paper')} — {entry['action']}",
            "score": entry.get("score", 0),
            "review_notes": entry.get("detail", ""),
            "changes_made": "",
            "diff_stats": {"lines_added": 0, "lines_removed": 0, "lines_changed": 0, "similarity_pct": 0},
        })

    # Review summary
    scores = [e["score"] for e in version_records if e["score"] and e["score"] > 0]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    review_summary = (
        f"v2 pipeline complete — {len(sections)} sections, "
        f"{len(scores)} reviews, average score: {avg_score}/10."
    )

    logger.info("generate_paper_v2: %s (post %s)", review_summary, post_id)

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
        "roundtable_reviews": [
            {
                "reviewer_id": r["reviewer_id"],
                "reviewer_name": r["reviewer_name"],
                "modeled_after": r.get("modeled_after", ""),
                "focus": r["focus"],
                "avatar": r.get("avatar", ""),
                "color": r.get("color", ""),
                "score": r["score"],
                "strengths": r.get("strengths", []),
                "weaknesses": r.get("weaknesses", []),
                "suggestions": r.get("suggestions", []),
                "critical_issues": r.get("critical_issues", []),
            }
            for r in roundtable_reviews
        ],
    }


# ---------------------------------------------------------------------------
# Resume: continue a failed pipeline from its last checkpoint
# ---------------------------------------------------------------------------


async def resume_paper_v2(
    blog_post_id: uuid.UUID,
    db: AsyncSession,
) -> Dict:
    """Resume a failed paper pipeline from its last checkpoint.

    Reads the BlogPost tags to determine the last completed phase,
    then continues from the next phase.

    Checkpoint tags used by the pipeline:
      - step:plan_complete  -> Phase 1 done
      - step:draft_complete -> Phase 2 done
      - step:merge_complete -> Phase 3 done
      - step:complete       -> fully done
    """
    result = await db.execute(select(BlogPost).where(BlogPost.id == blog_post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise ValueError(f"Paper not found: {blog_post_id}")

    tags = post.tags or []

    # Determine last completed step
    last_step: Optional[str] = None
    for tag in tags:
        if tag.startswith("step:"):
            last_step = tag.replace("step:", "")

    if last_step == "complete":
        return {
            "blog_post_id": str(blog_post_id),
            "title": post.title,
            "final_content": post.content,
            "status": "already_complete",
            "message": "This paper is already complete.",
        }

    agent_log = AgentLog()
    agents = create_pipeline_agents(agent_log)

    # Resolve venue from tags if present
    venue: Optional[VenueGuidelines] = None
    venue_tag = next((t for t in tags if t.startswith("venue:")), None)
    if venue_tag:
        venue_name = venue_tag.replace("venue:", "")
        try:
            venue = await resolve_venue(venue_name, db)
        except Exception:
            logger.warning("resume_paper_v2: could not resolve venue '%s'", venue_name)

    if last_step in ("draft_complete", "merge_complete"):
        # Resume from Phase 3: ROUNDTABLE REVIEW
        # The draft content is already in post.content
        logger.info("resume_paper_v2: resuming from %s for post %s", last_step, blog_post_id)
        agent_log.add("system", "resume", f"Resuming from {last_step}")

        editor = agents["gemini_editor"]
        writer = agents["gemini_writer"]
        venue_text = _venue_block(venue) if venue else ""

        paper = post.content

        # Run roundtable review
        all_reviews: List[Dict] = []
        for round_num in range(1, MAX_ROUNDTABLE_ROUNDS + 1):
            reviews = await run_review_roundtable(paper, venue_text, agent_log)
            all_reviews = reviews
            brief = build_revision_brief(reviews)
            min_score = min(r["score"] for r in reviews) if reviews else 0

            revision_user = (
                f"## Paper to Revise\n\n{paper}\n\n{brief}\n\n{venue_text}\n\n"
                "Address ALL critical issues. Return the COMPLETE revised paper."
            )
            paper = await writer.complete(
                system=_WRITER_REVISE_SYSTEM,
                user=revision_user,
                action="roundtable_revision",
                section=f"round_{round_num}",
            )
            if min_score >= MIN_SCORE_FOR_PASS:
                break

        # Phase 4: FINALIZE
        bibtex = ""
        latex_content: Optional[str] = None
        template = "arxiv"
        if venue and venue.template:
            template = venue.template
        try:
            latex_content, _ = await export_to_latex(paper, bibtex, template=template)
        except Exception:
            logger.exception("resume_paper_v2: LaTeX export failed")

        # Mark complete
        final_tags = ["paper", "v2", "progress:100", "step:complete"]
        if venue:
            final_tags.append(f"venue:{venue.venue_name}")
        await update_blog_post(
            post_id=blog_post_id,
            data=BlogPostUpdate(
                content=paper,
                tags=final_tags,
                change_note="Pipeline resumed and completed",
            ),
            db=db,
        )

        return {
            "blog_post_id": str(blog_post_id),
            "title": post.title,
            "final_content": paper,
            "bibtex": bibtex,
            "latex": latex_content,
            "versions": [],
            "review_summary": f"Resumed from {last_step}, roundtable review complete",
            "agent_log": agent_log.to_list(),
            "venue_guidelines": venue.to_dict() if venue else None,
            "roundtable_reviews": [
                {
                    "reviewer_id": r["reviewer_id"],
                    "reviewer_name": r["reviewer_name"],
                    "modeled_after": r.get("modeled_after", ""),
                    "focus": r["focus"],
                    "avatar": r.get("avatar", ""),
                    "color": r.get("color", ""),
                    "score": r["score"],
                    "strengths": r.get("strengths", []),
                    "weaknesses": r.get("weaknesses", []),
                    "suggestions": r.get("suggestions", []),
                    "critical_issues": r.get("critical_issues", []),
                }
                for r in all_reviews
            ],
        }

    # If no checkpoint or only plan_complete, we can't easily resume
    # (would need to re-run from scratch since we don't store section data)
    return {
        "blog_post_id": str(blog_post_id),
        "title": post.title,
        "final_content": post.content,
        "status": "cannot_resume",
        "message": f"Pipeline stopped at '{last_step or 'unknown'}'. Re-generate the paper to restart.",
    }


# ---------------------------------------------------------------------------
# Portfolio entry point: generate_portfolio_paper_v2
# ---------------------------------------------------------------------------

async def generate_portfolio_paper_v2(
    project_ids: List[uuid.UUID],
    paper_type: str,
    title: str,
    target_venue: Optional[str],
    additional_instructions: Optional[str],
    db: AsyncSession,
) -> Dict:
    """Run the v2 multi-agent pipeline for a multi-project portfolio paper."""
    from app.services.paper_service import _build_portfolio_paper_context

    agent_log = AgentLog()
    agents = create_pipeline_agents(agent_log)
    first_project_id = project_ids[0]

    # Resolve venue
    venue: Optional[VenueGuidelines] = None
    if target_venue:
        try:
            venue = await resolve_venue(target_venue, db)
            agent_log.add(
                "gemini_planner", "venue_resolved",
                f"Venue: {venue.venue_name}, source: {venue.source}",
            )
        except Exception:
            logger.exception(
                "generate_portfolio_paper_v2: venue resolution failed for '%s'", target_venue
            )

    # Build multi-project context
    logger.info(
        "generate_portfolio_paper_v2: building context for %d projects", len(project_ids)
    )
    context_block, papers = await _build_portfolio_paper_context(project_ids, db)

    if additional_instructions:
        context_block += f"\n\n## Additional Instructions\n{additional_instructions}"

    # Phase 1: PLAN
    logger.info("generate_portfolio_paper_v2: Phase 1 — PLAN")
    sections = await _phase_plan(
        agents["gemini_planner"], title, paper_type, context_block, venue,
    )
    total_steps = len(sections) + 3

    # Create BlogPost under first project
    post = await create_blog_post(
        project_id=first_project_id,
        data=BlogPostCreate(
            title=title,
            content="",
            status="draft",
            tags=_progress_tags("plan_complete", 1, total_steps),
        ),
        db=db,
    )
    post_id = post.id
    logger.info("generate_portfolio_paper_v2: created BlogPost %s", post_id)

    # Phase 2: DRAFT
    logger.info(
        "generate_portfolio_paper_v2: Phase 2 — DRAFT (%d sections)", len(sections)
    )
    written_sections = await _phase_draft(agents, sections, context_block, venue)

    partial_content = "\n\n".join(
        written_sections.get(str(s["number"]), "")
        for s in sections
        if written_sections.get(str(s["number"]))
    )
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=partial_content,
            tags=_progress_tags("draft_complete", len(sections) + 1, total_steps),
            change_note="All sections drafted",
        ),
        db=db,
    )

    # Phase 3: ROUNDTABLE REVIEW
    logger.info("generate_portfolio_paper_v2: Phase 3 — ROUNDTABLE REVIEW")
    final_content, roundtable_reviews = await _phase_roundtable_review(
        agents, sections, written_sections, venue,
    )

    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=final_content,
            tags=_progress_tags("merge_complete", len(sections) + 2, total_steps),
            change_note="Roundtable review complete",
        ),
        db=db,
    )

    # Phase 4: FINALIZE
    logger.info("generate_portfolio_paper_v2: Phase 4 — FINALIZE")
    bibtex = await _phase_finalize(papers)

    template = venue.template if venue and venue.template else "arxiv"
    latex_content: Optional[str] = None
    try:
        latex_content, _ = await export_to_latex(final_content, bibtex, template=template)
        logger.info(
            "generate_portfolio_paper_v2: LaTeX export succeeded (template: %s)", template
        )
    except Exception:
        logger.exception("generate_portfolio_paper_v2: LaTeX export failed")

    # Mark complete
    final_tags = ["paper", "portfolio", "v2", "progress:100", "step:complete"]
    if venue:
        final_tags.append(f"venue:{venue.venue_name}")
    await update_blog_post(
        post_id=post_id,
        data=BlogPostUpdate(
            content=final_content,
            tags=final_tags,
            change_note="Pipeline complete",
        ),
        db=db,
    )

    # Build version records from agent log scored entries
    version_records: List[Dict] = []
    scored_entries = [e for e in agent_log.entries if e.get("score") is not None]
    for idx, entry in enumerate(scored_entries, start=1):
        version_records.append({
            "version": idx,
            "review_name": f"{entry.get('section', 'full paper')} — {entry['action']}",
            "score": entry.get("score", 0),
            "review_notes": entry.get("detail", ""),
            "changes_made": "",
            "diff_stats": {
                "lines_added": 0, "lines_removed": 0, "lines_changed": 0, "similarity_pct": 0,
            },
        })

    scores = [e["score"] for e in version_records if e["score"] and e["score"] > 0]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    review_summary = (
        f"v2 portfolio pipeline: {len(sections)} sections, "
        f"{len(scores)} reviews, average score: {avg_score}/10."
    )

    logger.info("generate_portfolio_paper_v2: %s (post %s)", review_summary, post_id)

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
        "roundtable_reviews": [
            {
                "reviewer_id": r["reviewer_id"],
                "reviewer_name": r["reviewer_name"],
                "modeled_after": r.get("modeled_after", ""),
                "focus": r["focus"],
                "avatar": r.get("avatar", ""),
                "color": r.get("color", ""),
                "score": r["score"],
                "strengths": r.get("strengths", []),
                "weaknesses": r.get("weaknesses", []),
                "suggestions": r.get("suggestions", []),
                "critical_issues": r.get("critical_issues", []),
            }
            for r in roundtable_reviews
        ],
    }


# ---------------------------------------------------------------------------
# Edit paper (post-generation)
# ---------------------------------------------------------------------------

async def edit_paper(
    blog_post_id: uuid.UUID,
    instruction: str,
    target_section: Optional[str],
    target_pages: Optional[int],
    target_venue: Optional[str],
    db: AsyncSession,
) -> Dict:
    """Apply an edit to an existing paper (condense, section edit, or free-form).

    Returns a dict with: blog_post_id, updated_content, previous_version,
    new_version, changes_summary, agent_log, sections_modified.
    """
    # Load existing BlogPost
    result = await db.execute(select(BlogPost).where(BlogPost.id == blog_post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise ValueError(f"BlogPost {blog_post_id} not found")

    previous_content = post.content
    project_id = post.project_id

    # Determine previous version number
    ver_result = await db.execute(
        select(BlogPostVersion.version)
        .where(BlogPostVersion.blog_post_id == blog_post_id)
        .order_by(BlogPostVersion.version.desc())
        .limit(1)
    )
    previous_version = ver_result.scalar_one_or_none() or 1

    # Create agents
    agent_log = AgentLog()
    agents = create_pipeline_agents(agent_log)
    editor = agents["gemini_editor"]
    critic = agents["openai_critic"]

    # Resolve venue if provided
    venue: Optional[VenueGuidelines] = None
    if target_venue:
        try:
            venue = await resolve_venue(target_venue, db)
            agent_log.add(
                "system", "venue_resolved",
                f"Edit venue: {venue.venue_name} (page_limit: {venue.page_limit})",
            )
        except Exception:
            logger.exception("edit_paper: venue resolution failed for '%s'", target_venue)

    venue_text = _venue_block(venue)
    sections_modified: List[str] = []

    # --- Detect edit type ---
    instruction_lower = instruction.lower()
    is_condense = (
        "condense" in instruction_lower
        or "shorten" in instruction_lower
        or "compress" in instruction_lower
        or target_pages is not None
    )
    is_section_edit = target_section is not None

    if is_condense:
        # --- Condense edit ---
        page_target = target_pages
        if page_target is None and venue and venue.page_limit:
            page_target = venue.page_limit
        if page_target is None:
            # Default: reduce by 30%
            current_pages = _estimate_pages(previous_content)
            page_target = max(1, int(current_pages * 0.7))

        agent_log.add(
            "system", "edit_type",
            f"Condense edit — target: {page_target} pages",
        )

        condense_user = (
            f"## Full Paper\n{previous_content}\n\n"
            f"## Instruction\n{instruction}\n\n"
            f"Target: {page_target} pages (~{page_target * 300} words).\n"
            f"Current estimate: ~{_estimate_pages(previous_content)} pages.\n"
            f"{venue_text}\n\n"
            "Condense the paper. Output the COMPLETE condensed paper."
        )
        updated_content = await editor.complete(
            system=_EDITOR_CONDENSE_SYSTEM,
            user=condense_user,
            action="condense_edit",
        )
        sections_modified = ["all"]

    elif is_section_edit:
        # --- Section edit ---
        agent_log.add(
            "system", "edit_type",
            f"Section edit — target: {target_section}",
        )

        edit_user = (
            f"## Full Paper\n{previous_content}\n\n"
            f"## Instruction\nModify ONLY section '{target_section}' as follows: "
            f"{instruction}\n\n"
            f"{venue_text}\n\n"
            "Output the COMPLETE paper with only that section modified. "
            "All other sections must remain unchanged."
        )
        updated_content = await editor.complete(
            system=_EDITOR_COHERENCE_SYSTEM,
            user=edit_user,
            action="section_edit",
            section=target_section,
        )
        sections_modified = [target_section]

    else:
        # --- Free-form edit: planner first decides target section, editor then applies ---
        agent_log.add(
            "system", "edit_type",
            f"Free-form edit: {instruction[:100]}",
        )

        planner = agents["gemini_planner"]
        decide_user = (
            "Decide where in this paper the user's instruction belongs.\n\n"
            "Output ONLY a JSON object (no markdown fences, no prose):\n"
            "{\n"
            '  "scope": "section" or "global",\n'
            '  "target_section": "<number or heading match, only if scope=section>",\n'
            '  "rationale": "<one sentence>"\n'
            "}\n\n"
            "Use 'section' when the instruction adds/modifies content that belongs in ONE existing section. "
            "Use 'global' only when the instruction truly affects the whole paper (e.g., 'reduce length', "
            "'change tone', 'add inline citations everywhere').\n\n"
            f"## Instruction\n{instruction}\n\n"
            f"## Paper headings (numbered list, in order)\n"
            f"{_extract_headings(previous_content)}\n"
        )
        decision = await planner.complete_json(
            system=_PLANNER_INSERT_DECIDE_SYSTEM,
            user=decide_user,
            action="freeform_decide",
        )
        scope = decision.get("scope", "global")
        target_section = decision.get("target_section", "").strip()
        agent_log.add(
            "gemini_planner", "freeform_decide",
            f"Decided scope={scope}, target_section={target_section!r}: "
            f"{decision.get('rationale', '')}",
        )

        if scope == "section" and target_section:
            freeform_user = (
                f"## Full Paper\n{previous_content}\n\n"
                f"## Instruction\nApply this change to section '{target_section}': "
                f"{instruction}\n\n"
                f"{venue_text}\n\n"
                "Hard rules: return the COMPLETE paper. ALL sections in order, "
                "headings preserved, citations preserved. Make the change ONLY in the "
                f"target section ('{target_section}'). All other sections unchanged."
            )
            sections_modified = [target_section]
        else:
            freeform_user = (
                f"## Full Paper\n{previous_content}\n\n"
                f"## Instruction\n{instruction}\n\n"
                f"{venue_text}\n\n"
                "Hard rules: return the COMPLETE paper. ALL sections in their original "
                "order, headings preserved, citations preserved. Apply the instruction "
                "globally as needed."
            )
            sections_modified = ["all"]

        updated_content = await editor.complete(
            system=_EDITOR_COHERENCE_SYSTEM,
            user=freeform_user,
            action="freeform_edit",
        )

    # --- Critic review on the result ---
    review_user = (
        f"Review the edited paper for overall quality and coherence.\n"
        f"{venue_text}\n\n"
        f"## Edited Paper\n{updated_content}\n\n"
        "Output your JSON review."
    )
    review_result = await critic.complete_json(
        system=_CRITIC_SECTION_SYSTEM,
        user=review_user,
        action="edit_review",
    )
    edit_score = _safe_score(review_result.get("score", 0))
    edit_critique = review_result.get("critique", "")
    agent_log.add(
        "openai_critic", "edit_review",
        f"Edit review score {edit_score}/10: {edit_critique[:150]}",
        score=edit_score,
    )

    # --- Save as new version ---
    diff_stats = compute_diff_stats(previous_content, updated_content)
    changes_summary = (
        f"{instruction[:80]} — "
        f"{diff_stats['lines_added']} lines added, "
        f"{diff_stats['lines_removed']} removed "
        f"({diff_stats['similarity_pct']}% similar), "
        f"critic score: {edit_score}/10"
    )

    await update_blog_post(
        post_id=blog_post_id,
        data=BlogPostUpdate(
            content=updated_content,
            change_note=changes_summary,
        ),
        db=db,
    )

    # Determine new version number
    new_ver_result = await db.execute(
        select(BlogPostVersion.version)
        .where(BlogPostVersion.blog_post_id == blog_post_id)
        .order_by(BlogPostVersion.version.desc())
        .limit(1)
    )
    new_version = new_ver_result.scalar_one_or_none() or (previous_version + 1)

    return {
        "blog_post_id": str(blog_post_id),
        "updated_content": updated_content,
        "previous_version": previous_version,
        "new_version": new_version,
        "changes_summary": changes_summary,
        "agent_log": agent_log.to_list(),
        "sections_modified": sections_modified,
    }
