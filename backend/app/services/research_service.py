"""
Research Assistant service — ARIS-inspired academic writing assistant.

Uses project context (narrative, repo, workspace) plus real academic literature
from Semantic Scholar to produce citation-backed research writing.

Messages are stored in the shared chat_messages table and tagged with
metadata_ = {"role_type": "research"} to separate them from co-founder chat.
"""
import asyncio
import logging
import re
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage
from app.models.project import Project
from app.services.ai_client import get_cloud_client
from app.services.narrative_service import build_context_block, get_or_create
from app.services.paper_reviewers import (
    REVIEWER_REGISTRY,
    get_reviewer,
    route_to_research_reviewers,
)
from app.services.repo_context import get_generation_context
from app.services import knowledge_extractor
from app.services.scholar_service import (
    find_related_work,
    format_papers_for_prompt,
    search_papers,
)
from app.services.workspace_scanner import get_latest_snapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — high quality academic writing assistant
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM = """You are a world-class research writing assistant embedded in ProjectScribe. \
You combine deep knowledge of the user's projects with real academic literature from Semantic Scholar.

YOUR CAPABILITIES:
- Literature search and synthesis with REAL citations (never fabricate references)
- Grant proposal drafting (NIH, NSF, EU Horizon style)
- Conference paper writing (abstract, introduction, methods, results, discussion)
- Technical report and white paper drafting
- Literature review generation with citation-backed claims
- Research gap identification
- Methodology section writing from actual codebase

CITATION RULES — STRICTLY ENFORCED:
- Only cite papers explicitly listed in the "Available Literature" context block provided to you
- Use [N] numbered notation matching the numbers in the context block exactly
- Never hallucinate paper titles, author names, years, or DOIs
- If no relevant papers are available in context, say so rather than inventing references
- Every factual claim about the literature must link to a [N] citation
- Do not mix citation styles — use [N] inline and include a References section at the end

QUALITY STANDARDS:
- Every claim must be backed by either project data or a real paper citation from context
- Write in formal academic tone appropriate for the target venue
- Structure arguments logically: problem → gap → contribution → evidence
- Include specific technical details from the project's actual codebase and architecture when available

WRITING STYLE:
- Active voice where possible ("We propose..." not "It is proposed...")
- Precise technical language, no buzzwords or marketing speak
- Quantitative claims where data exists in the project context
- Proper academic hedging ("results suggest" vs "results prove")
- Clear topic sentences for each paragraph
- Paragraphs of 3-6 sentences; avoid one-sentence paragraphs

ARIS-INSPIRED WRITING PIPELINE:
When the user requests a research document, follow this pipeline explicitly:
1. UNDERSTAND: Extract key concepts from the project context (what problem, what approach, what contribution)
2. POSITION: Identify where the project fits in the literature landscape using the provided papers
3. GAP: Articulate the specific gap that this work addresses, citing prior work that falls short
4. DRAFT: Write the requested section with [N] citations throughout
5. REVIEW: At the end, check every claim is supported — flag any claim without a citation as "(unsupported — needs citation)"

AVAILABLE RESEARCH TEMPLATES:
When the user says "use template X" or asks for a specific document type, apply:
- grant_proposal: NIH/NSF structure — Specific Aims, Significance, Innovation, Approach
- conference_abstract: 250-word structured abstract (Background/Objective, Methods, Results, Conclusion)
- paper_intro: Introduction section — motivation, prior work survey, contribution statement, paper structure
- paper_methods: Methods section — derived from actual system architecture in the codebase
- literature_review: Structured related work — thematic organisation, gap analysis, transition to contribution
- technical_report: Full technical report — Executive Summary, Introduction, Methods, Results, Discussion, Conclusion
- white_paper: Industry-facing document — Problem, Solution, Technical Approach, Evidence, Call to Action

TONE ADAPTATION:
- For NIH/NSF grants: measured, evidence-dense, impact-forward
- For conference papers (ACM, IEEE): precise, technical, reproducibility-focused
- For white papers: accessible to non-experts, value-proposition clear
- For literature reviews: balanced, critical, comparative"""


# ---------------------------------------------------------------------------
# Conversation starters
# ---------------------------------------------------------------------------

RESEARCH_STARTERS = [
    {
        "category": "Literature",
        "prompts": [
            "Find related work for this project",
            "What's the research gap my project addresses?",
            "Who are the key researchers in this field?",
        ],
    },
    {
        "category": "Writing",
        "prompts": [
            "Draft a conference abstract for this project",
            "Write an introduction section positioning my work",
            "Help me write a methods section from the codebase",
        ],
    },
    {
        "category": "Proposals",
        "prompts": [
            "Draft an NSF-style grant proposal for this project",
            "What's the significance and innovation of this work?",
            "Help me articulate the broader impacts",
        ],
    },
    {
        "category": "Strategy",
        "prompts": [
            "Which conferences should I submit this to?",
            "What experiments would strengthen a paper submission?",
            "How should I frame this for a health informatics audience?",
        ],
    },
    {
        "category": "Visuals",
        "prompts": [
            "Generate a comparison table for this project vs alternatives",
            "Create an architecture diagram from the codebase",
            "Suggest 5 paper titles for this project",
            "Help me design evaluation metrics and results table",
        ],
    },
]


# ---------------------------------------------------------------------------
# Metadata tag used to identify research messages in the shared table
# ---------------------------------------------------------------------------

_RESEARCH_ROLE_TYPE = "research"


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

def _extract_research_keywords(ctx: dict) -> List[str]:
    """
    Pull research-relevant keywords from the narrative context dict.

    Combines: one_liner words, target_audience, and origin_story snippets
    to produce a list of meaningful keyword phrases for Semantic Scholar queries.
    """
    keywords: List[str] = []

    one_liner = ctx.get("one_liner") or ""
    if one_liner:
        keywords.append(one_liner)

    target_audience = ctx.get("target_audience") or ""
    if target_audience:
        keywords.append(target_audience)

    # Pull significant phrases from origin story (first sentence only)
    origin_story = ctx.get("origin_story") or ""
    if origin_story:
        first_sentence = origin_story.split(".")[0].strip()
        if first_sentence and len(first_sentence) > 10:
            keywords.append(first_sentence[:120])

    # Include preferred angles as they often name research areas
    preferred_angles = ctx.get("preferred_angles") or []
    keywords.extend(str(a) for a in preferred_angles[:2] if a)

    # Deduplicate while preserving order
    seen: set = set()
    unique: List[str] = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower not in seen and len(kw.strip()) > 3:
            seen.add(kw_lower)
            unique.append(kw)

    return unique[:5]  # cap at 5 to avoid excessive API calls


async def _build_research_context(
    project_id: uuid.UUID,
    user_message: str,
    include_literature: bool,
    include_workspace: bool,
    include_repo: bool,
    db: AsyncSession,
) -> str:
    """
    Assemble a research-specific context block for the AI.

    Layers (in order of inclusion):
    1. Project narrative (always)
    2. GitHub repo context (if include_repo and project has github_repo)
    3. Local workspace snapshot (if include_workspace)
    4. Semantic Scholar related papers (if include_literature)

    The literature block uses a numbered [N] format the AI is instructed to cite.
    """
    from sqlalchemy import select as sa_select

    sections: List[str] = []
    narrative_ctx: dict = {}

    # -- Project narrative --
    try:
        narrative = await get_or_create(project_id, db)
        narrative_ctx = build_context_block(narrative)
        narrative_parts: List[str] = []
        if narrative_ctx.get("one_liner"):
            narrative_parts.append(f"One-liner: {narrative_ctx['one_liner']}")
        if narrative_ctx.get("target_audience"):
            narrative_parts.append(f"Target audience: {narrative_ctx['target_audience']}")
        if narrative_ctx.get("origin_story"):
            narrative_parts.append(f"Origin story: {narrative_ctx['origin_story']}")
        if narrative_ctx.get("tone_notes"):
            narrative_parts.append(f"Tone notes: {narrative_ctx['tone_notes']}")
        if narrative_ctx.get("preferred_angles"):
            narrative_parts.append(
                f"Research angles: {', '.join(narrative_ctx['preferred_angles'])}"
            )
        if narrative_parts:
            sections.append("## Project Narrative\n" + "\n".join(narrative_parts))
    except Exception:
        logger.exception("Failed to load narrative for research context: project %s", project_id)

    # -- GitHub repo context (provides methods/architecture grounding) --
    if include_repo:
        try:
            result = await db.execute(
                sa_select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project and project.github_repo:
                repo_ctx = await get_generation_context(project.github_repo, is_private=False)
                if repo_ctx and repo_ctx.strip():
                    if len(repo_ctx) > 6000:
                        repo_ctx = repo_ctx[:6000] + "\n\n[... truncated ...]"
                    sections.append(f"## Repository Context (for methods grounding)\n{repo_ctx}")
        except Exception:
            logger.exception("Failed to fetch repo context for research: project %s", project_id)

    # -- Local workspace snapshot --
    if include_workspace:
        try:
            snapshot = await get_latest_snapshot(project_id, db)
            if snapshot:
                ws_parts: List[str] = [snapshot.summary]
                if snapshot.git_branch:
                    ws_parts.append(f"\nCurrent branch: {snapshot.git_branch}")
                sections.append("## Local Workspace (architecture/methods context)\n" + "\n".join(ws_parts))
        except Exception:
            logger.exception("Failed to load workspace snapshot for research: project %s", project_id)

    # -- Semantic Scholar literature --
    if include_literature:
        try:
            keywords = _extract_research_keywords(narrative_ctx)
            # Also extract keywords from the user's current message for targeted search
            # (e.g. if user says "find papers on federated learning" we want to search that)
            message_keywords = _extract_message_keywords(user_message)
            all_keywords = message_keywords + keywords if message_keywords else keywords

            if all_keywords:
                papers = await find_related_work(all_keywords, limit=15)
                if papers:
                    lit_block = format_papers_for_prompt(papers)
                    sections.append(lit_block)
                else:
                    sections.append(
                        "## Available Literature\n"
                        "No papers found via Semantic Scholar for the current project keywords. "
                        "Ask the user to provide specific search terms or paper IDs."
                    )
            else:
                sections.append(
                    "## Available Literature\n"
                    "Insufficient project narrative to generate search keywords. "
                    "Complete the project narrative (one-liner, description) to enable literature search."
                )
        except Exception:
            logger.exception("Semantic Scholar search failed for research context: project %s", project_id)

    return "\n\n".join(sections)


def _extract_message_keywords(message: str) -> List[str]:
    """
    Extract potential research query terms from the user's message.

    Looks for phrases following patterns like "find papers on X", "search for X",
    "related to X", "about X". Returns up to 2 keyword phrases.
    """
    patterns = [
        r"(?:find|search|look up|papers? on|research on|literature on|related to|about)\s+([^,.?!]{5,80})",
    ]
    keywords: List[str] = []
    for pattern in patterns:
        matches = re.findall(pattern, message, re.IGNORECASE)
        for match in matches:
            kw = match.strip()
            if kw and kw not in keywords:
                keywords.append(kw)
    return keywords[:2]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_research_message(
    project_id: uuid.UUID,
    user_message: str,
    include_literature: bool,
    include_workspace: bool,
    include_repo: bool,
    db: AsyncSession,
    reviewer_id: Optional[str] = None,
) -> Tuple[List[ChatMessage], List[str], str]:
    """
    Process a research assistant message via the reviewer roundtable:
    1. Persist the user message (tagged as research)
    2. Build research context (narrative + repo + workspace + literature)
    3. Load research conversation history
    4. Compose user prompt with context + history
    5. Route to reviewers (or use specific reviewer_id)
    6. Parallel dispatch via asyncio.gather
    7. Return (messages_list, routed_reviewer_ids, roundtable_group)
    """
    # 1. Persist user message with research tag
    user_msg = ChatMessage(
        project_id=project_id,
        role="user",
        content=user_message,
        metadata_={"role_type": _RESEARCH_ROLE_TYPE},
    )
    db.add(user_msg)
    await db.flush()

    # 2. Build research context block
    context_block = await _build_research_context(
        project_id=project_id,
        user_message=user_message,
        include_literature=include_literature,
        include_workspace=include_workspace,
        include_repo=include_repo,
        db=db,
    )

    # 3. Fetch research conversation history (last 20 messages, research only)
    history_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.project_id == project_id,
            ChatMessage.id != user_msg.id,
            ChatMessage.metadata_["role_type"].astext == _RESEARCH_ROLE_TYPE,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    history: List[ChatMessage] = list(reversed(history_result.scalars().all()))

    # 4. Compose the user prompt that carries context + history + new message
    user_prompt_parts: List[str] = []

    if context_block.strip():
        user_prompt_parts.append(
            f"## Research Context\n\n{context_block}\n\n---\n"
        )

    if history:
        history_lines: List[str] = []
        for msg in history:
            role_label = "Researcher" if msg.role == "user" else "Assistant"
            reviewer_label = ""
            if msg.metadata_ and msg.metadata_.get("reviewer_id"):
                reviewer_name = msg.metadata_.get("reviewer_name", msg.metadata_["reviewer_id"])
                reviewer_label = f" [{reviewer_name}]"
            # Truncate long history entries but keep more for research (academic content is dense)
            content = msg.content if len(msg.content) <= 1500 else msg.content[:1500] + "..."
            history_lines.append(f"**{role_label}{reviewer_label}:** {content}")
        user_prompt_parts.append(
            "## Conversation History\n\n" + "\n\n".join(history_lines) + "\n\n---\n"
        )

    user_prompt_parts.append(f"**Researcher:** {user_message}")
    user_prompt = "\n".join(user_prompt_parts)

    # 5. Route to reviewers
    if reviewer_id and reviewer_id in REVIEWER_REGISTRY:
        routed_ids = [reviewer_id]
    else:
        routed_ids = await route_to_research_reviewers(user_message)

    # 6. Parallel dispatch
    roundtable_group = str(uuid.uuid4())[:8]
    ai = get_cloud_client()

    async def _call_reviewer(rid: str, index: int) -> ChatMessage:
        reviewer = get_reviewer(rid)
        if reviewer is None:
            reviewer = get_reviewer("technical_rigor")

        # Combine reviewer persona with research system context.
        # Strip the JSON output suffix — reviewers act as conversational advisors here,
        # not structured paper reviewers.
        base_prompt = reviewer.system_prompt
        # The _OUTPUT_SUFFIX starts with "\nOUTPUT FORMAT"
        suffix_marker = "\nOUTPUT FORMAT"
        if suffix_marker in base_prompt:
            base_prompt = base_prompt[:base_prompt.index(suffix_marker)]

        system = (
            f"{base_prompt}\n\n"
            f"ADDITIONAL CONTEXT: You are also acting as a research advisor in a chat conversation. "
            f"When the researcher asks questions, provide detailed, citation-aware advice from your "
            f"perspective as {reviewer.modeled_after}. Reference specific papers from the literature "
            f"context when relevant. Use [N] citation notation matching the numbered papers in context.\n\n"
            f"RESEARCH ASSISTANT GUIDELINES:\n{RESEARCH_SYSTEM}"
        )

        try:
            reply_text = await ai.complete(system=system, user=user_prompt)
        except Exception:
            logger.exception("Research reviewer %s failed", rid)
            reply_text = "I encountered an error generating a response. Please try again."

        msg = ChatMessage(
            project_id=project_id,
            role="assistant",
            content=reply_text,
            metadata_={
                "role_type": _RESEARCH_ROLE_TYPE,
                "reviewer_id": rid,
                "reviewer_name": reviewer.name,
                "modeled_after": reviewer.modeled_after,
                "avatar": reviewer.avatar,
                "color": reviewer.color,
                "roundtable_group": roundtable_group,
                "roundtable_index": index,
                "routed_reviewers": routed_ids,
                "include_literature": include_literature,
                "include_workspace": include_workspace,
                "include_repo": include_repo,
            },
        )
        return msg

    tasks = [_call_reviewer(rid, idx) for idx, rid in enumerate(routed_ids)]
    reviewer_messages = await asyncio.gather(*tasks)

    # Add all messages to session AFTER gather completes (single-threaded, safe)
    for msg in reviewer_messages:
        db.add(msg)
    await db.flush()
    for msg in reviewer_messages:
        await db.refresh(msg)

    try:
        from app.services.event_stream import emit
        emit(
            "info",
            "ai.complete",
            f"{len(reviewer_messages)} reviewer{'s' if len(reviewer_messages) != 1 else ''} replied",
            project_id=str(project_id),
            meta={"count": len(reviewer_messages), "kind": "research"},
        )
    except Exception:
        logger.exception("event emit failed (non-fatal)")

    # Commit so background extraction tasks see the just-persisted messages
    # and so concurrent extraction tasks see each other's writes (the per-user
    # lock plus a committed view together prevent dedup races).
    try:
        await db.commit()
    except Exception:
        logger.exception("commit before bg extraction failed; skipping extraction")
    else:
        try:
            project = await db.get(Project, project_id)
            owner_user_id = project.user_id if project else None
        except Exception:
            logger.exception("could not resolve project owner for knowledge extraction")
            owner_user_id = None

        if owner_user_id is not None:
            for ai_msg in reviewer_messages:
                asyncio.create_task(knowledge_extractor.bg_extract_from_turn(
                    user_id=owner_user_id,
                    project_id=project_id,
                    user_msg_id=user_msg.id,
                    user_msg_content=user_msg.content,
                    ai_msg_id=ai_msg.id,
                    ai_msg_content=ai_msg.content,
                    conversation_kind="research",
                ))

    return list(reviewer_messages), routed_ids, roundtable_group


async def get_research_history(
    project_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[ChatMessage], int]:
    """
    Return a page of research messages (oldest-first) and the total count.

    Filters to only messages tagged with role_type == "research".
    """
    # Count research messages only
    total_result = await db.execute(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.project_id == project_id,
            ChatMessage.metadata_["role_type"].astext == _RESEARCH_ROLE_TYPE,
        )
    )
    total: int = total_result.scalar_one()

    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.project_id == project_id,
            ChatMessage.metadata_["role_type"].astext == _RESEARCH_ROLE_TYPE,
        )
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    messages = list(result.scalars().all())
    return messages, total


async def clear_research_history(project_id: uuid.UUID, db: AsyncSession) -> int:
    """
    Delete all research messages for the project.

    Only removes messages tagged as role_type == "research".
    Co-founder chat messages are not affected.
    Returns the number of messages deleted.
    """
    from sqlalchemy import delete

    result = await db.execute(
        delete(ChatMessage).where(
            ChatMessage.project_id == project_id,
            ChatMessage.metadata_["role_type"].astext == _RESEARCH_ROLE_TYPE,
        )
    )
    return result.rowcount
