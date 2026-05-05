"""
Chat service: Co-Founder AI conversation.

Manages conversation history, assembles rich context (narrative, repo, workspace,
memory, recent drafts/blogs), calls the cloud AI, and persists both the user
message and the assistant reply.
"""
import asyncio
import logging
import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.blog import BlogPost
from app.models.chat import ChatMessage
from app.models.draft import Draft
from app.models.project import Project
from app.services import knowledge_extractor
from app.services.ai_client import get_cloud_client
from app.services.advisors import ADVISOR_REGISTRY, get_advisor, route_to_advisors
from app.services.memory_service import search_memory
from app.services.narrative_service import build_context_block, get_or_create
from app.services.repo_context import get_generation_context
from app.services.workspace_scanner import get_latest_snapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

CO_FOUNDER_SYSTEM = """You are a YC-trained strategic advisor and co-founder embedded in \
ProjectScribe, the user's project management tool. You operate with the depth of a YC partner \
who has read all their code, studied their commit history, and knows their portfolio cold.

ABOUT THE FOUNDER YOU'RE ADVISING:
- Solo developer (GitHub: Chesterguan) managing 8+ projects simultaneously
- Portfolio includes: PSDL, HAVEN, Prometheno, veritas, cliniclaw, psdl-inspector, PSDL-workbench
- Primary domains: health tech, data infrastructure, developer tooling
- Currently wearing all hats: CEO + CTO. You provide the CFO + advisor perspective.

YOUR ADVISOR ROLES (adapt based on what the conversation needs):
- CFO lens: Revenue model viability, burn rate awareness, runway, unit economics, pricing strategy
- YC Partner lens: Idea clarity, market size, PMF signals, competitive moat, growth metrics
- Investor lens: Pitch readiness, fundraising timing, valuation benchmarks, due diligence prep
- Growth Strategist lens: Distribution channels, marketing angles, partnership opportunities, virality

YC FRAMEWORKS YOU APPLY (use these by name when relevant):

1. YC'S 7 QUESTIONS — apply to any project being evaluated:
   Q1: What do you do? (Can you explain it in one sentence to a non-technical person?)
   Q2: How big is the market? (TAM/SAM/SOM — be specific, no "trillion dollar" hand-waving)
   Q3: What's your progress? (Users, revenue, retention, growth rate — concrete numbers)
   Q4: What's your unique insight? (Why will this work when others have failed?)
   Q5: What's the business model? (How do you make money, and what are the unit economics?)
   Q6: What's the team? (Solo founder risk — mitigate with speed and AI leverage)
   Q7: What's the ask? (What do you need right now — users, capital, partnerships, hires?)

2. STAGE DETECTION — automatically assess which stage a project is in and calibrate advice:
   PRE-LAUNCH: No users yet. Focus = ship an MVP in days not weeks, then talk to 20+ users.
   POST-LAUNCH / PRE-PMF: Has users but unclear retention. Focus = retention loops, iteration speed.
   PMF: Users are retained, some are paying or showing "very disappointed" signals. Focus = growth.
   GROWTH: Proven model, now scaling. Focus = hiring, fundraising, distribution at scale.

3. METRICS THAT MATTER BY STAGE:
   Pre-launch: Days to MVP, number of user interviews conducted
   Pre-PMF: Weekly active users, D7/D30 retention, qualitative "hair-on-fire" signals
   PMF test: Sean Ellis score (>40% "very disappointed" if product disappeared = PMF signal)
   Growth: MoM revenue growth (>15% = good, >20% = great), churn rate (<5% monthly for SaaS),
           LTV:CAC ratio (>3:1), ARR, NPS

4. PAUL GRAHAM PRINCIPLES (cite these when applicable):
   "Make something people want" — validation beats vision every time
   "Do things that don't scale" — manual processes first, automate later
   "Startup = Growth" — if you're not growing, you're dying
   "Talk to users" — most founder mistakes come from not doing this enough
   "Launch fast and iterate" — a shipped product beats a perfect spec

5. SAM ALTMAN: FOCUS AND INTENSITY
   "The most important thing is to make something people want, and focus."
   Solo founders building multiple projects simultaneously is a red flag — it dilutes focus.
   Dominate one market segment before expanding. Speed compounds.

6. GARRY TAN: AI-FIRST SOLO FOUNDER FRAMEWORK
   A single founder leveraging AI tools can now reach $10-20M ARR with 10-20 people.
   The constraint is no longer headcount — it's focus, distribution, and PMF speed.
   Every hour spent on the wrong project is catastrophic at solo-founder scale.

7. GSTACK OFFICE HOURS — 6 FORCING QUESTIONS (use when evaluating any new idea or feature):
   Q1: DEMAND REALITY — Is there real demand, or are you building for imagined users?
   Q2: STATUS QUO — What do people do today without your solution? How painful is it really?
   Q3: DESPERATE SPECIFICITY — Who is desperately waiting for this? Can you name 5 real people?
   Q4: NARROWEST WEDGE — What is the smallest version that solves one painful problem completely?
   Q5: OBSERVATION & SURPRISE — What have you observed that surprised you? What's non-obvious?
   Q6: FUTURE-FIT — Will this matter more or less in 2-3 years? Is the trend your friend?

8. CEO REVIEW SCOPE MODES (use when discussing project direction):
   SCOPE EXPANSION: Dream big — what's the 10-star version? What would make this a $1B company?
   SELECTIVE EXPANSION: Hold current scope but cherry-pick one bold expansion
   HOLD SCOPE: Maximum rigor on current plan — cut everything non-essential
   SCOPE REDUCTION: Strip to absolute essentials — what's the 1-week MVP?

BEHAVIOR RULES:
- Always ground advice in actual project data from the context provided (repo, workspace, memory)
- When giving strategic advice, reference specific YC frameworks by name
- Challenge assumptions directly: "Have you talked to 20+ users about this?" is a valid question
- Be honest about readiness: "This isn't ready for investors yet because X" is more helpful than encouragement
- Ask probing questions when the user is vague — do not accept "it's going well" without numbers
- Provide specific action items with clear owners (even if the owner is always the same person)
- Build on previous conversation context — track what was discussed earlier and reference it
- When a founder is spread too thin, say so explicitly and recommend which project to cut or pause
- If the project data shows recent commits but no releases, flag it — shipping is the job

TONE:
- Direct and honest, like a YC partner in an office hours session — not a cheerleader
- Confident but intellectually honest — say "I don't know" when data is absent
- Challenging without being dismissive — push back hard on weak assumptions, support good ones
- Actionable — every response should end with at least one specific next step"""


# ---------------------------------------------------------------------------
# Strategic conversation starters
# ---------------------------------------------------------------------------

STRATEGIC_STARTERS = [
    # Stage & Focus
    {
        "category": "Stage & Focus",
        "prompts": [
            "What stage is this project at? What should I focus on?",
            "Am I ready to apply to YC with this project?",
        ],
    },
    # Business & Revenue
    {
        "category": "Business & Revenue",
        "prompts": [
            "How should I monetize this project?",
            "What's my addressable market size?",
        ],
    },
    # Growth & Users
    {
        "category": "Growth & Users",
        "prompts": [
            "How do I get my first 10 users?",
            "What distribution channels should I try?",
        ],
    },
    # Pitch & Fundraising
    {
        "category": "Pitch & Fundraising",
        "prompts": [
            "Help me write a 2-sentence pitch for this project",
            "What questions would a YC partner ask about this?",
        ],
    },
    # Portfolio
    {
        "category": "Portfolio",
        "prompts": [
            "Which of my projects has the best market potential?",
            "Should I focus on one project or keep building multiple?",
        ],
    },
]


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

async def _build_chat_context(
    project_id: uuid.UUID,
    user_message: str,
    include_workspace: bool,
    include_memory: bool,
    include_repo: bool,
    db: AsyncSession,
) -> str:
    """
    Assemble a rich context block to prepend to the AI conversation.

    Pulls from:
    - Project narrative (always included)
    - GitHub repo context (if include_repo and project has github_repo)
    - Workspace snapshot (if include_workspace and a snapshot exists)
    - Semantic memory search (if include_memory)
    - Recent drafts (last 3 titles/platforms)
    - Recent blog posts (last 3 titles)
    """
    from sqlalchemy import select as sa_select

    sections: List[str] = []

    # -- Project narrative --
    try:
        narrative = await get_or_create(project_id, db)
        ctx = build_context_block(narrative)
        narrative_parts: List[str] = []
        if ctx.get("one_liner"):
            narrative_parts.append(f"One-liner: {ctx['one_liner']}")
        if ctx.get("target_audience"):
            narrative_parts.append(f"Target audience: {ctx['target_audience']}")
        if ctx.get("origin_story"):
            narrative_parts.append(f"Origin story: {ctx['origin_story']}")
        if ctx.get("tone_notes"):
            narrative_parts.append(f"Tone notes: {ctx['tone_notes']}")
        if ctx.get("preferred_angles"):
            narrative_parts.append(f"Preferred angles: {', '.join(ctx['preferred_angles'])}")
        if narrative_parts:
            sections.append("## Project Narrative\n" + "\n".join(narrative_parts))
    except Exception:
        logger.exception("Failed to load narrative for project %s", project_id)

    # -- GitHub repo context --
    if include_repo:
        try:
            result = await db.execute(
                sa_select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project and project.github_repo:
                is_private = False  # assume public; could be stored on project
                repo_ctx = await get_generation_context(project.github_repo, is_private=is_private)
                if repo_ctx and repo_ctx.strip():
                    # Truncate to keep total context manageable
                    if len(repo_ctx) > 5000:
                        repo_ctx = repo_ctx[:5000] + "\n\n[... truncated ...]"
                    sections.append(f"## Repository Context\n{repo_ctx}")
        except Exception:
            logger.exception("Failed to fetch repo context for project %s", project_id)

    # -- Workspace snapshot --
    if include_workspace:
        try:
            snapshot = await get_latest_snapshot(project_id, db)
            if snapshot:
                ws_parts: List[str] = [snapshot.summary]
                if snapshot.git_branch:
                    ws_parts.append(f"\nCurrent branch: {snapshot.git_branch}")
                if snapshot.git_status:
                    ws_parts.append(f"Git status:\n{snapshot.git_status}")
                sections.append("## Local Workspace\n" + "\n".join(ws_parts))
        except Exception:
            logger.exception("Failed to load workspace snapshot for project %s", project_id)

    # -- Memory search --
    if include_memory:
        try:
            memories = await search_memory(project_id, user_message, limit=5, db=db)
            if memories:
                mem_lines = [f"- {m.content[:300]}" for m in memories]
                sections.append("## Relevant Memory\n" + "\n".join(mem_lines))
        except Exception:
            logger.exception("Memory search failed for project %s", project_id)

    # -- Knowledge graph --
    if include_memory:
        try:
            from app.services.knowledge_service import search_knowledge
            proj_result = await db.execute(
                sa_select(Project).where(Project.id == project_id)
            )
            project = proj_result.scalar_one_or_none()
            owner_user_id = project.user_id if project else None
            if owner_user_id is not None:
                hits = await search_knowledge(
                    user_id=owner_user_id, query=user_message, db=db,
                    project_id=project_id, limit=5,
                )
                if hits:
                    k_lines = [
                        f"- [{h.node.node_type}] {h.node.title} — {h.node.content[:200]}"
                        for h in hits
                    ]
                    sections.append("## Relevant Knowledge\n" + "\n".join(k_lines))
        except Exception:
            logger.exception("knowledge search failed for project %s (non-fatal)", project_id)

    # -- Recent drafts --
    try:
        draft_result = await db.execute(
            sa_select(Draft)
            .where(Draft.project_id == project_id, Draft.parent_draft_id.is_(None))
            .order_by(Draft.created_at.desc())
            .limit(3)
        )
        recent_drafts = list(draft_result.scalars().all())
        if recent_drafts:
            draft_lines = [
                f"- [{d.platform}] {d.title or '(no title)'} ({d.status})"
                for d in recent_drafts
            ]
            sections.append("## Recent Drafts\n" + "\n".join(draft_lines))
    except Exception:
        logger.exception("Failed to load recent drafts for project %s", project_id)

    # -- Recent blog posts --
    try:
        blog_result = await db.execute(
            sa_select(BlogPost)
            .where(BlogPost.project_id == project_id)
            .order_by(BlogPost.created_at.desc())
            .limit(3)
        )
        recent_blogs = list(blog_result.scalars().all())
        if recent_blogs:
            blog_lines = [f"- {b.title} ({b.status})" for b in recent_blogs]
            sections.append("## Recent Blog Posts\n" + "\n".join(blog_lines))
    except Exception:
        logger.exception("Failed to load recent blog posts for project %s", project_id)

    # -- Project stage assessment --
    # Infer the project's current stage from available signals so the advisor
    # can calibrate its framing (pre-launch vs. post-launch vs. PMF vs. growth).
    try:
        stage_signals: List[str] = []
        detected_stage = "Pre-launch"

        # Check for workspace snapshot (indicates active local development)
        has_workspace = any("## Local Workspace" in s for s in sections)
        has_repo = any("## Repository Context" in s for s in sections)

        # Check for published drafts or blog posts as a proxy for public presence
        published_drafts = 0
        published_blogs = 0
        try:
            pd_result = await db.execute(
                sa_select(Draft)
                .where(Draft.project_id == project_id, Draft.status == "published")
                .limit(1)
            )
            published_drafts = len(list(pd_result.scalars().all()))
        except Exception:
            pass
        try:
            pb_result = await db.execute(
                sa_select(BlogPost)
                .where(BlogPost.project_id == project_id, BlogPost.status == "published")
                .limit(1)
            )
            published_blogs = len(list(pb_result.scalars().all()))
        except Exception:
            pass

        has_published_content = (published_drafts + published_blogs) > 0

        # Memory entries suggest iterative learning — indicative of post-launch iteration
        has_memory = any("## Relevant Memory" in s for s in sections)

        # Stage inference heuristic (no revenue/user data available at this layer,
        # so we use publishing activity and development signals)
        if has_published_content and has_memory:
            detected_stage = "Post-launch / Pre-PMF"
            stage_signals.append("Has published content — project is externally visible")
            stage_signals.append("Has accumulated memory entries — iterating based on learnings")
        elif has_published_content:
            detected_stage = "Post-launch / Pre-PMF"
            stage_signals.append("Has published content — project is externally visible")
            stage_signals.append("No memory entries yet — not yet incorporating user feedback loops")
        elif has_repo and has_workspace:
            detected_stage = "Pre-launch (active development)"
            stage_signals.append("Active repo + local workspace — building but not yet shipping")
        elif has_repo:
            detected_stage = "Pre-launch"
            stage_signals.append("Repo exists but no workspace snapshot — development activity unclear")
        else:
            detected_stage = "Pre-launch (early)"
            stage_signals.append("No repo or workspace data — project may be ideation-only")

        stage_lines = [f"Detected stage: {detected_stage}"] + [f"- {sig}" for sig in stage_signals]
        stage_lines.append(
            "Note: Stage detection is heuristic. Correct this if actual user/revenue data is known."
        )
        sections.append("## Project Stage Assessment\n" + "\n".join(stage_lines))
    except Exception:
        logger.exception("Failed to assess project stage for %s", project_id)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_message(
    project_id: uuid.UUID,
    user_message: str,
    include_workspace: bool,
    include_memory: bool,
    include_repo: bool,
    db: AsyncSession,
    advisor_id: Optional[str] = None,
) -> Tuple[List[ChatMessage], List[str], str]:
    """
    Store the user message, route to advisors, dispatch in parallel, store replies.

    Returns: (advisor_messages, routed_advisor_ids, roundtable_group)
    """
    # 1. Persist user message
    user_msg = ChatMessage(
        project_id=project_id,
        role="user",
        content=user_message,
    )
    db.add(user_msg)
    await db.flush()

    # 2. Build rich context block
    context_block = await _build_chat_context(
        project_id=project_id,
        user_message=user_message,
        include_workspace=include_workspace,
        include_memory=include_memory,
        include_repo=include_repo,
        db=db,
    )

    # 3. Build conversation history (last 20 messages)
    history_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.project_id == project_id,
            ChatMessage.id != user_msg.id,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    history: List[ChatMessage] = list(reversed(history_result.scalars().all()))

    # 4. Compose user prompt with context + history
    user_prompt_parts: List[str] = []
    if context_block.strip():
        user_prompt_parts.append(f"## Project Context\n\n{context_block}\n\n---\n")
    if history:
        history_lines: List[str] = []
        for msg in history:
            role_label = "User" if msg.role == "user" else "Assistant"
            content = msg.content if len(msg.content) <= 1000 else msg.content[:1000] + "..."
            advisor_label = ""
            if msg.metadata_ and msg.metadata_.get("advisor_id"):
                advisor_name = msg.metadata_.get("advisor_name", msg.metadata_["advisor_id"])
                advisor_label = f" [{advisor_name}]"
            history_lines.append(f"**{role_label}{advisor_label}:** {content}")
        user_prompt_parts.append(
            "## Conversation History\n\n" + "\n\n".join(history_lines) + "\n\n---\n"
        )
    user_prompt_parts.append(f"**User:** {user_message}")
    user_prompt = "\n".join(user_prompt_parts)

    # 5. Route to advisors
    if advisor_id and advisor_id in ADVISOR_REGISTRY:
        routed_ids = [advisor_id]
    else:
        routed_ids = await route_to_advisors(user_message)

    # 6. Dispatch in parallel
    roundtable_group = str(uuid.uuid4())[:8]
    ai = get_cloud_client()

    async def _call_advisor(aid: str, index: int) -> ChatMessage:
        advisor = get_advisor(aid)
        if advisor is None:
            advisor = get_advisor("yc_partner")

        # YC partner uses the original detailed system prompt
        if aid == "yc_partner":
            system = CO_FOUNDER_SYSTEM
        else:
            system = advisor.system_prompt

        try:
            reply_text = await ai.complete(system=system, user=user_prompt)
        except Exception:
            logger.exception("Advisor %s call failed", aid)
            reply_text = "I encountered an error generating a response. Please try again."

        msg = ChatMessage(
            project_id=project_id,
            role="assistant",
            content=reply_text,
            metadata_={
                "advisor_id": aid,
                "advisor_name": advisor.name,
                "roundtable_group": roundtable_group,
                "roundtable_index": index,
                "routed_advisors": routed_ids,
                "include_workspace": include_workspace,
                "include_memory": include_memory,
                "include_repo": include_repo,
            },
        )
        return msg

    tasks = [_call_advisor(aid, idx) for idx, aid in enumerate(routed_ids)]
    advisor_messages = await asyncio.gather(*tasks)

    # Add all messages to session AFTER gather completes (single-threaded, safe)
    for msg in advisor_messages:
        db.add(msg)
    await db.flush()
    for msg in advisor_messages:
        await db.refresh(msg)

    # Fire-and-forget knowledge extraction per advisor reply.
    # We resolve user_id from the Project row; if unavailable we skip silently.
    try:
        project = await db.get(Project, project_id)
        owner_user_id = project.user_id if project else None
    except Exception:
        logger.exception("could not resolve project owner for knowledge extraction")
        owner_user_id = None

    if owner_user_id is not None:
        for ai_msg in advisor_messages:
            asyncio.create_task(knowledge_extractor.bg_extract_from_turn(
                user_id=owner_user_id,
                project_id=project_id,
                user_msg_id=user_msg.id,
                user_msg_content=user_msg.content,
                ai_msg_id=ai_msg.id,
                ai_msg_content=ai_msg.content,
                conversation_kind="cofounder",
            ))

    return list(advisor_messages), routed_ids, roundtable_group


async def get_history(
    project_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[ChatMessage], int]:
    """
    Return a page of chat messages (oldest-first) and the total count.
    """
    total_result = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.project_id == project_id)
    )
    total: int = total_result.scalar_one()

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    messages = list(result.scalars().all())
    return messages, total


async def clear_history(project_id: uuid.UUID, db: AsyncSession) -> int:
    """Delete all chat messages for the project. Returns the number deleted."""
    from sqlalchemy import delete
    result = await db.execute(
        delete(ChatMessage).where(ChatMessage.project_id == project_id)
    )
    return result.rowcount
