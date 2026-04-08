# Co-Founder Roundtable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-advisor Co-Founder chat with a roundtable of 8 named advisors, with smart routing to pick 3-4 per question, parallel dispatch, and separate chat bubbles with AI portrait avatars.

**Architecture:** New `advisors.py` module defines 8 advisor configs with system prompts. Router agent (lightweight Gemini call) selects 3-4 relevant advisors per question. `chat_service.send_message()` dispatches in parallel via `asyncio.gather()`, stores each response as a separate `ChatMessage` with advisor metadata in the existing JSONB column. Frontend groups responses by `roundtable_group` and renders each with an advisor avatar badge.

**Tech Stack:** Python 3.9+ (FastAPI, asyncio), Gemini Flash (router + advisors), Next.js 16, shadcn/ui, Tailwind

**Spec:** `docs/superpowers/specs/2026-04-06-co-founder-roundtable-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|----------------|
| `backend/app/services/advisors.py` | Advisor registry (8 configs with system prompts), `route_to_advisors()` router agent, `get_advisor()`, `get_all_advisors()` |
| `frontend/lib/advisors.ts` | Frontend advisor registry mirror (id, name, tagline, color, avatar — no prompts) |
| `frontend/components/chat/AdvisorCard.tsx` | Reusable advisor avatar card (lg for picker, sm for message badge) |
| `frontend/components/chat/RoundtableGroup.tsx` | Wrapper that groups 3-4 advisor messages with a shared header |
| `frontend/public/avatars/yc_partner.png` | Placeholder avatar images (8 files) |
| `frontend/public/avatars/elon_musk.png` | |
| `frontend/public/avatars/alex_hormozi.png` | |
| `frontend/public/avatars/greg_isenberg.png` | |
| `frontend/public/avatars/nathan_gotch.png` | |
| `frontend/public/avatars/julia_mccoy.png` | |
| `frontend/public/avatars/growth_tribe.png` | |
| `frontend/public/avatars/dan_koe.png` | |

### Modified files

| File | Changes |
|------|---------|
| `backend/app/services/chat_service.py` | `send_message()` gains `advisor_id` param, router dispatch, parallel `asyncio.gather()`, multi-message response |
| `backend/app/schemas/chat.py` | Add `advisor_id` to request, `ChatRoundtableResponse`, `AdvisorInfo` schema |
| `backend/app/routers/chat.py` | POST returns `ChatRoundtableResponse`, new `GET /chat/advisors` endpoint |
| `frontend/lib/types.ts` | Add `ChatRoundtableResponse`, `AdvisorInfo`, `advisor_id` on `ChatMessage` and `ChatSendRequest` |
| `frontend/lib/api.ts` | `chat.send()` returns `ChatRoundtableResponse`, add `chat.advisors()` |
| `frontend/components/chat/ChatWindow.tsx` | Advisor picker bar, roundtable grouping logic, updated send handler |
| `frontend/components/chat/ChatMessage.tsx` | Advisor badge (avatar + name), color accent border |

---

## Task 1: Advisor Registry

**Files:**
- Create: `backend/app/services/advisors.py`

- [ ] **Step 1: Create the advisors module with configs and system prompts**

This is a large file (~600 lines) containing all 8 advisor system prompts plus the router. The full code:

```python
"""
Advisor registry for the Co-Founder Roundtable.

Each advisor has a unique persona, system prompt, expertise tags, and visual identity.
The router agent selects 3-4 advisors per question based on expertise tag matching.
"""
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.agents import AgentLog, NamedAgent, extract_json
from app.services.ai_client import get_cloud_client

logger = logging.getLogger(__name__)


@dataclass
class AdvisorConfig:
    id: str
    name: str
    tagline: str
    expertise: List[str]
    color: str
    avatar: str
    system_prompt: str


# ---------------------------------------------------------------------------
# Common suffix appended to every advisor's system prompt
# ---------------------------------------------------------------------------

_COMMON_SUFFIX = """
CONTEXT RULES:
- Ground all advice in the actual project context provided (repo, narrative, workspace, memory)
- Be specific to THIS project — no generic platitudes
- Reference actual data when available (commits, tech stack, recent activity)
- Keep responses to 2-3 focused paragraphs — concise and actionable
- End with ONE specific next step the founder should take this week
- If you lack data to answer confidently, say so — don't fabricate

TONE:
- Speak in first person as yourself — "I'd approach this by..." not generic advice
- Be direct, opinionated, and confident in your domain
- Challenge weak assumptions but respect the founder's constraints
- You're a co-founder, not a consultant — you have skin in the game"""


# ---------------------------------------------------------------------------
# Advisor system prompts
# ---------------------------------------------------------------------------

_ELON_MUSK_PROMPT = """You are a co-founder who thinks like Elon Musk. Your superpower is first principles \
reasoning — decomposing problems to fundamental truths and rebuilding from there.

YOUR FRAMEWORKS:

1. FIRST PRINCIPLES DECOMPOSITION
   Don't reason by analogy ("other companies do X"). Instead ask:
   - What are the fundamental truths here?
   - What are we assuming that might be wrong?
   - If we started from scratch knowing only the physics/economics, what would we build?

2. 10X vs 10% THINKING
   A 10% improvement means competing within existing paradigms.
   A 10x improvement means changing the paradigm entirely.
   Always ask: "Is there a way to make this 10x better, not 10% better?"

3. VERTICAL INTEGRATION
   When a critical dependency is controlled by others, you're fragile.
   Consider: should we build this ourselves? What's the long-term cost of depending on X?

4. PHYSICS-BASED TIMELINES
   "If the schedule is long, it's wrong. If the cost is high, it's wrong."
   Production should be the hard part, not the product design.
   Identify the rate-limiting step and attack it directly.

5. MANUFACTURING MINDSET
   The product is easy. The factory that builds the factory is hard.
   Think about scalability of the process, not just the output.
   Automate ruthlessly. If a human is doing it, ask why.

6. RISK CALIBRATION
   Take big risks on things that matter. Derisk everything else.
   "Failure is an option here. If things are not failing, you are not innovating enough."
""" + _COMMON_SUFFIX

_ALEX_HORMOZI_PROMPT = """You are a co-founder who thinks like Alex Hormozi. Your superpower is turning any \
product into an irresistible offer with clear unit economics.

YOUR FRAMEWORKS:

1. THE VALUE EQUATION
   Value = (Dream Outcome x Perceived Likelihood of Achievement) / (Time Delay x Effort & Sacrifice)
   To increase value: increase the dream outcome or likelihood, decrease time or effort.
   Most founders try to lower price. Instead, increase perceived value.

2. GRAND SLAM OFFER DESIGN
   A Grand Slam Offer has: dream outcome + perceived likelihood + time frame + effort minimized.
   Stack bonuses that solve adjacent problems. Make the offer so good people feel stupid saying no.
   "If you're competing on price, you've already lost."

3. LEAD MAGNET -> CORE -> PROFIT MAXIMIZER
   Level 1: Free value that solves a narrow problem (lead magnet)
   Level 2: Core offer that solves the main problem (your product)
   Level 3: Profit maximizer that solves the next problem (upsell/premium)
   Build all three. Most founders only build Level 2.

4. THE $100M LENS
   Would this business model work at $100M revenue? If not, the model is wrong.
   What would the unit economics look like? What's the LTV:CAC at scale?

5. VOLUME x LEVERAGE
   Revenue = Volume of leads x Conversion rate x Average order value x Purchase frequency.
   Identify which variable is weakest and attack it.

6. NAMING & FRAMING
   The name of your offer matters more than you think.
   Reframe the category. Don't sell "software" — sell "the system that does X."
""" + _COMMON_SUFFIX

_GREG_ISENBERG_PROMPT = """You are a co-founder who thinks like Greg Isenberg. Your superpower is community-led \
growth and building products that people feel they belong to.

YOUR FRAMEWORKS:

1. COMMUNITY-LED GROWTH
   Build the audience before the product. A community of 1000 engaged people is worth
   more than 100K passive visitors. The community tells you what to build.

2. MINIMUM VIABLE COMMUNITY (MVC)
   Before building product: create a space (Discord, Slack, newsletter) around the problem.
   If you can't get 100 people to join and engage, the problem isn't painful enough.
   The MVC validates demand without writing a line of code.

3. STARTUP IDEA FORMULA
   Startup = Audience + Problem + Monetization
   Start with the audience you can reach. What problem do they share?
   "The best startups are built by people who are their own target user."

4. SOCIAL PRODUCT THINKING
   Products that spread have social mechanics built in:
   - Identity: Does using this say something about who I am?
   - Status: Does this give me social currency?
   - Belonging: Do I feel part of something?

5. RETENTION THROUGH BELONGING
   Retention isn't about features — it's about identity.
   People don't churn from communities they identify with.
   Build rituals, shared language, and insider knowledge.

6. MICRO-SAAS ECONOMICS
   You don't need VC. A $20/mo product with 2500 users = $50K MRR.
   Find a niche, own it completely, expand only when it's boring.
""" + _COMMON_SUFFIX

_NATHAN_GOTCH_PROMPT = """You are a co-founder who thinks like Nathan Gotch. Your superpower is organic growth \
through SEO and content-led acquisition that compounds over time.

YOUR FRAMEWORKS:

1. SEO AUTHORITY FLYWHEEL
   Create content -> rank for keywords -> earn traffic -> get links -> increase authority -> rank harder keywords.
   This flywheel takes 6-12 months to spin up but then compounds indefinitely.
   "SEO traffic is the only traffic that gets cheaper over time."

2. TOPICAL AUTHORITY
   Google rewards depth over breadth. Cover one topic exhaustively before expanding.
   Map every subtopic. Create content for each. Interlink them all.

3. KEYWORD-DRIVEN CONTENT STRATEGY
   Every piece of content starts with a keyword. No keyword = no traffic intent.
   Prioritize: high intent + low competition + relevant to your product.
   Map keywords to funnel stage: awareness -> consideration -> decision.

4. PROGRAMMATIC SEO FOR SAAS
   Create template pages that scale: "/tool-for-{use-case}", "/{city}-{service}".
   One template, thousands of pages. Each targets a long-tail keyword.

5. LINK BUILDING AS LEVERAGE
   Links = votes of confidence from other sites. More links from quality sites = higher rankings.
   Strategies: guest posting, resource page links, digital PR, creating linkable assets.

6. CONTENT COMPOUND GROWTH
   One article can drive traffic for 5+ years. Paid ads stop when you stop paying.
   Invest in evergreen content that compounds. Update annually to maintain rankings.
""" + _COMMON_SUFFIX

_JULIA_MCCOY_PROMPT = """You are a co-founder who thinks like Julia McCoy. Your superpower is using AI to create \
content at scale while building a personal brand that becomes your distribution moat.

YOUR FRAMEWORKS:

1. AI CONTENT AT SCALE
   Use AI for first drafts, research, and repurposing. Use humans for strategy, voice, and editing.
   "AI is the engine, you're the driver." The strategy and brand voice must be human-led.
   One piece of long-form content -> 10+ derivative pieces across platforms.

2. PERSONAL BRAND AS DISTRIBUTION MOAT
   Your personal brand is the one asset competitors can't copy.
   People follow people, not companies. The founder IS the brand in early stages.
   Build in public. Share the journey. Be the face of your product.

3. CONTENT-LED GROWTH FRAMEWORK
   Phase 1: SEO-driven blog content (long-term compounding)
   Phase 2: Social media presence (short-term engagement)
   Phase 3: Email newsletter (owned audience — platform-independent)
   Phase 4: Repurpose everything across channels

4. THE CONTENT STOREFRONT
   "Content is the new storefront." People research before they buy.
   Your blog, YouTube, social presence = the front door to your business.

5. BRAND VOICE CONSISTENCY
   Define your brand voice in 3 adjectives. Every piece of content must match.
   Consistency builds trust. Trust builds audience. Audience builds revenue.

6. THOUGHT LEADERSHIP POSITIONING
   Don't create content about everything. Own one topic deeply.
   Be the person people think of when they think of X.
""" + _COMMON_SUFFIX

_GROWTH_TRIBE_PROMPT = """You are a co-founder who thinks like the Growth Tribe team. Your superpower is \
systematic experimentation and data-driven growth across the full funnel.

YOUR FRAMEWORKS:

1. AARRR PIRATE METRICS
   Acquisition -> Activation -> Retention -> Revenue -> Referral.
   Measure each stage. Find the biggest drop-off. Fix that first.
   Most founders optimize acquisition when the real problem is activation or retention.

2. ICE SCORING FOR EXPERIMENTS
   For every growth idea, score: Impact (1-10) x Confidence (1-10) x Ease (1-10).
   Run highest-ICE experiments first. Kill experiments that don't show signal in 2 weeks.
   "Run 10 experiments per week. Most will fail. The ones that work change everything."

3. NORTH STAR METRIC
   One metric that captures the core value your product delivers.
   Airbnb: Nights booked. Slack: Messages sent. What's yours?
   Every experiment should move the North Star.

4. GROWTH MODEL MAPPING
   Draw the growth model: how does one user lead to the next?
   Identify every loop: viral loop, content loop, paid loop, sales loop.
   Strengthen the strongest loop first.

5. RAPID EXPERIMENTATION CULTURE
   Hypothesis -> Test -> Measure -> Learn -> Repeat.
   Document every experiment: what you tested, what happened, what you learned.

6. DATA-DRIVEN DECISION MAKING
   "In God we trust. All others bring data."
   Set up analytics before building features. If you can't measure it, don't build it.
   Cohort analysis over vanity metrics. Week-over-week retention over total signups.
""" + _COMMON_SUFFIX

_DAN_KOE_PROMPT = """You are a co-founder who thinks like Dan Koe. Your superpower is building leveraged \
one-person businesses using digital products and personal brand.

YOUR FRAMEWORKS:

1. DIGITAL ECONOMICS
   "Sell your mind, not your time." Digital products have zero marginal cost.
   Create once, sell infinitely: courses, templates, software, communities.
   The goal is removing yourself from the delivery of value.

2. ONE-PERSON BUSINESS LEVERAGE
   Solo does not equal small. With AI and automation, one person can build a $1-5M/year business.
   Leverage stack: code, content, capital, collaboration.
   Hire only when you've automated everything automatable.

3. EDUCATION-BASED MARKETING
   Teach what you know. Teaching builds trust faster than any ad.
   Free education -> paid implementation. Give away the "what", sell the "how".
   "The best marketing doesn't feel like marketing."

4. NICHE OF ONE
   Don't pick a niche — BE the niche. Your unique intersection of skills + interests + experience.
   You are the only person with your exact combination. That IS your positioning.
   Solve your own problems. Document the solution. Sell it to people like you.

5. THE 4-HOUR CONTENT SYSTEM
   Write one long-form piece per week (newsletter/blog). Spend 4 focused hours.
   Decompose into: 5-7 social posts, 1 thread, 1 video script.
   One idea, many formats. Consistency > volume.

6. FOCUS AS COMPETITIVE ADVANTAGE
   "The person who can focus the longest wins."
   One project. One audience. One offer. Master it before expanding.
   Distraction is the enemy. Every new idea is a threat to the current one.
""" + _COMMON_SUFFIX


# ---------------------------------------------------------------------------
# Advisor Registry
# ---------------------------------------------------------------------------

ADVISOR_REGISTRY: Dict[str, AdvisorConfig] = {
    "yc_partner": AdvisorConfig(
        id="yc_partner",
        name="YC Partner",
        tagline="Startup Strategy & PMF",
        expertise=["startup", "pmf", "fundraising", "metrics", "pitch", "growth", "revenue"],
        color="#F59E0B",
        avatar="/avatars/yc_partner.png",
        system_prompt="",  # uses existing CO_FOUNDER_SYSTEM from chat_service
    ),
    "elon_musk": AdvisorConfig(
        id="elon_musk",
        name="Elon Musk",
        tagline="First Principles & Moonshots",
        expertise=["scaling", "engineering", "vision", "first-principles", "moonshot", "automation"],
        color="#3B82F6",
        avatar="/avatars/elon_musk.png",
        system_prompt=_ELON_MUSK_PROMPT,
    ),
    "alex_hormozi": AdvisorConfig(
        id="alex_hormozi",
        name="Alex Hormozi",
        tagline="$100M Offers & Value",
        expertise=["pricing", "monetization", "offers", "leads", "sales", "value", "revenue"],
        color="#10B981",
        avatar="/avatars/alex_hormozi.png",
        system_prompt=_ALEX_HORMOZI_PROMPT,
    ),
    "greg_isenberg": AdvisorConfig(
        id="greg_isenberg",
        name="Greg Isenberg",
        tagline="Community-Led Growth",
        expertise=["community", "social", "audience", "virality", "retention", "micro-saas"],
        color="#8B5CF6",
        avatar="/avatars/greg_isenberg.png",
        system_prompt=_GREG_ISENBERG_PROMPT,
    ),
    "nathan_gotch": AdvisorConfig(
        id="nathan_gotch",
        name="Nathan Gotch",
        tagline="SEO & Organic Growth",
        expertise=["seo", "traffic", "organic-growth", "keywords", "content-marketing", "links"],
        color="#EC4899",
        avatar="/avatars/nathan_gotch.png",
        system_prompt=_NATHAN_GOTCH_PROMPT,
    ),
    "julia_mccoy": AdvisorConfig(
        id="julia_mccoy",
        name="Julia McCoy",
        tagline="AI Content Strategy",
        expertise=["content", "branding", "ai-content", "writing", "marketing", "personal-brand"],
        color="#F97316",
        avatar="/avatars/julia_mccoy.png",
        system_prompt=_JULIA_MCCOY_PROMPT,
    ),
    "growth_tribe": AdvisorConfig(
        id="growth_tribe",
        name="Growth Tribe",
        tagline="Growth Hacking & Experiments",
        expertise=["growth-hacking", "experiments", "analytics", "activation", "retention", "data"],
        color="#06B6D4",
        avatar="/avatars/growth_tribe.png",
        system_prompt=_GROWTH_TRIBE_PROMPT,
    ),
    "dan_koe": AdvisorConfig(
        id="dan_koe",
        name="Dan Koe",
        tagline="One-Person Business",
        expertise=["solopreneur", "leverage", "digital-products", "personal-brand", "focus", "content"],
        color="#EF4444",
        avatar="/avatars/dan_koe.png",
        system_prompt=_DAN_KOE_PROMPT,
    ),
}

DEFAULT_ADVISORS = ["yc_partner", "alex_hormozi", "dan_koe"]


def get_advisor(advisor_id: str) -> Optional[AdvisorConfig]:
    """Get an advisor config by ID. Returns None if not found."""
    return ADVISOR_REGISTRY.get(advisor_id)


def get_all_advisors() -> List[AdvisorConfig]:
    """Return all advisor configs (for the /chat/advisors endpoint)."""
    return list(ADVISOR_REGISTRY.values())


def get_advisor_info_list() -> List[Dict[str, Any]]:
    """Return advisor metadata dicts (no system prompts) for API responses."""
    return [
        {
            "id": a.id,
            "name": a.name,
            "tagline": a.tagline,
            "expertise": a.expertise,
            "color": a.color,
            "avatar": a.avatar,
        }
        for a in ADVISOR_REGISTRY.values()
    ]


# ---------------------------------------------------------------------------
# Router agent — selects 3-4 advisors per question
# ---------------------------------------------------------------------------

_ROUTER_SYSTEM = """You are a routing agent for a co-founder advisory team. Given a founder's question, \
select 3-4 advisors whose expertise is most relevant.

Rules:
- Pick 3-4 advisors (never fewer than 3, never more than 4)
- Always include yc_partner if the question involves startup strategy, fundraising, or metrics
- Match based on expertise tags, not just surface keywords
- If the question is broad ("what should I focus on?"), pick diverse perspectives

Output ONLY a JSON array of advisor IDs, ordered by relevance. No other text."""


async def route_to_advisors(user_message: str) -> List[str]:
    """
    Call the router agent to select 3-4 advisors for a user question.

    Returns a list of advisor IDs. Falls back to DEFAULT_ADVISORS on failure.
    """
    advisor_list = "\n".join(
        f"- {a.id}: {', '.join(a.expertise)}"
        for a in ADVISOR_REGISTRY.values()
    )

    user_prompt = (
        f"Available advisors:\n{advisor_list}\n\n"
        f'Question: "{user_message}"\n\n'
        "Output the JSON array of 3-4 advisor IDs:"
    )

    try:
        ai = get_cloud_client()
        raw = await ai.complete(system=_ROUTER_SYSTEM, user=user_prompt)
        data = extract_json(raw)

        # extract_json returns {} on failure; we need a list
        if isinstance(data, list):
            advisor_ids = data
        elif isinstance(data, dict):
            # Some models wrap in {"advisors": [...]}
            advisor_ids = data.get("advisors", [])
            if not advisor_ids:
                # Try to find any list value
                for v in data.values():
                    if isinstance(v, list):
                        advisor_ids = v
                        break
        else:
            advisor_ids = []

        # Validate: only keep IDs that exist in registry
        valid_ids = [aid for aid in advisor_ids if aid in ADVISOR_REGISTRY]

        if len(valid_ids) >= 3:
            return valid_ids[:4]

        logger.warning("route_to_advisors: got %d valid IDs, falling back", len(valid_ids))
        return DEFAULT_ADVISORS

    except Exception:
        logger.exception("route_to_advisors: router call failed, using defaults")
        return DEFAULT_ADVISORS
```

Note: `extract_json` from agents.py returns `{}` for non-JSON — but the router returns a JSON array `[...]`. We need to handle this. The code above parses the raw response, trying `json.loads()` directly for arrays. Let me fix `route_to_advisors` to handle arrays properly:

The `extract_json` in `agents.py` only finds `{...}` blocks. For the router which returns `[...]`, we parse the raw response directly in `route_to_advisors` using `json.loads`. Replace the try block's parsing section with:

```python
    try:
        ai = get_cloud_client()
        raw = await ai.complete(system=_ROUTER_SYSTEM, user=user_prompt)

        # Router returns a JSON array, not an object
        import json
        cleaned = raw.strip()
        # Strip markdown fences if present
        if cleaned.startswith("```"):
            import re
            match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()

        advisor_ids = json.loads(cleaned)
        if not isinstance(advisor_ids, list):
            advisor_ids = []

        # Validate: only keep IDs that exist in registry
        valid_ids = [str(aid) for aid in advisor_ids if str(aid) in ADVISOR_REGISTRY]

        if len(valid_ids) >= 3:
            return valid_ids[:4]

        logger.warning("route_to_advisors: got %d valid IDs, falling back", len(valid_ids))
        return DEFAULT_ADVISORS

    except Exception:
        logger.exception("route_to_advisors: router call failed, using defaults")
        return DEFAULT_ADVISORS
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
docker compose exec backend python -c "from app.services.advisors import ADVISOR_REGISTRY, route_to_advisors, get_advisor_info_list; print(f'OK: {len(ADVISOR_REGISTRY)} advisors')"
```
Expected: `OK: 8 advisors`

---

## Task 2: Backend Schemas

**Files:**
- Modify: `backend/app/schemas/chat.py`

- [ ] **Step 1: Add advisor_id to ChatSendRequest and new response schemas**

Replace the full content of `backend/app/schemas/chat.py` with:

```python
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class ChatSendRequest(BaseModel):
    message: str
    advisor_id: Optional[str] = None  # specific advisor, or None for roundtable
    # Context toggles — all default to True so the AI has full context by default
    include_workspace: bool = True
    include_memory: bool = True
    include_repo: bool = True


class ChatMessageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    role: str
    content: str
    # metadata_ is the Python attribute name; the column is "metadata"
    metadata_: Optional[dict]
    created_at: datetime
    # Advisor fields — extracted from metadata for convenience
    advisor_id: Optional[str] = None
    advisor_name: Optional[str] = None


class ChatRoundtableResponse(BaseModel):
    messages: List[ChatMessageResponse]
    routed_advisors: List[str]
    roundtable_group: str


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageResponse]
    total: int


class AdvisorInfo(BaseModel):
    id: str
    name: str
    tagline: str
    expertise: List[str]
    color: str
    avatar: str
```

---

## Task 3: Chat Service — Roundtable Dispatch

**Files:**
- Modify: `backend/app/services/chat_service.py`

This is the core change. The `send_message()` function is modified to support roundtable dispatch.

- [ ] **Step 1: Add roundtable imports and helper**

Add these imports at the top of `chat_service.py` (after existing imports):

```python
import asyncio
from app.services.advisors import (
    ADVISOR_REGISTRY,
    get_advisor,
    route_to_advisors,
)
```

- [ ] **Step 2: Modify send_message signature and add roundtable logic**

Replace the existing `send_message()` function with this version. The key changes are:
1. New `advisor_id` parameter
2. Router dispatch when no specific advisor selected
3. Parallel AI calls via `asyncio.gather()`
4. Returns a list of assistant messages instead of a single one

```python
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

    # 4. Compose the user prompt with context + history
    user_prompt_parts: List[str] = []
    if context_block.strip():
        user_prompt_parts.append(
            f"## Project Context\n\n{context_block}\n\n---\n"
        )
    if history:
        history_lines: List[str] = []
        for msg in history:
            role_label = "User" if msg.role == "user" else "Assistant"
            content = msg.content if len(msg.content) <= 1000 else msg.content[:1000] + "..."
            # Include advisor name if present
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
            reply_text = (
                f"I encountered an error generating a response. "
                f"Please try again."
            )

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
        db.add(msg)
        return msg

    tasks = [_call_advisor(aid, idx) for idx, aid in enumerate(routed_ids)]
    advisor_messages = await asyncio.gather(*tasks)

    await db.flush()
    for msg in advisor_messages:
        await db.refresh(msg)

    return list(advisor_messages), routed_ids, roundtable_group
```

---

## Task 4: Chat Router Endpoint

**Files:**
- Modify: `backend/app/routers/chat.py`

- [ ] **Step 1: Update imports and POST endpoint**

Replace the full content of `backend/app/routers/chat.py`:

```python
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.chat import ChatMessage
from app.models.project import Project
from app.schemas.chat import (
    AdvisorInfo,
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatRoundtableResponse,
    ChatSendRequest,
)
from app.services import chat_service
from app.services.advisors import get_advisor, get_advisor_info_list
from app.services.chat_service import STRATEGIC_STARTERS

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["chat"])

# Separate router for non-project-scoped chat endpoints
starters_router = APIRouter(prefix="/chat", tags=["chat"])


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _to_response(msg: ChatMessage) -> ChatMessageResponse:
    """Convert a ChatMessage ORM object to response schema with advisor fields."""
    advisor_id = None
    advisor_name = None
    if msg.metadata_:
        advisor_id = msg.metadata_.get("advisor_id")
        advisor_name = msg.metadata_.get("advisor_name")
    return ChatMessageResponse(
        id=msg.id,
        project_id=msg.project_id,
        role=msg.role,
        content=msg.content,
        metadata_=msg.metadata_,
        created_at=msg.created_at,
        advisor_id=advisor_id,
        advisor_name=advisor_name,
    )


@router.post("", response_model=ChatRoundtableResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    project_id: uuid.UUID,
    body: ChatSendRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ChatRoundtableResponse:
    """Send a message to the Co-Founder roundtable and receive advisor replies."""
    await _require_project(project_id, db)
    messages, routed_ids, group = await chat_service.send_message(
        project_id=project_id,
        user_message=body.message,
        include_workspace=body.include_workspace,
        include_memory=body.include_memory,
        include_repo=body.include_repo,
        advisor_id=body.advisor_id,
        db=db,
    )
    return ChatRoundtableResponse(
        messages=[_to_response(m) for m in messages],
        routed_advisors=routed_ids,
        roundtable_group=group,
    )


@router.get("", response_model=ChatHistoryResponse)
async def get_history(
    project_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ChatHistoryResponse:
    """Retrieve paginated chat history for the project (oldest-first)."""
    await _require_project(project_id, db)
    messages, total = await chat_service.get_history(project_id, db, limit=limit, offset=offset)
    return ChatHistoryResponse(
        messages=[_to_response(m) for m in messages],
        total=total,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> None:
    """Delete all chat messages for the project."""
    await _require_project(project_id, db)
    await chat_service.clear_history(project_id, db)


# ---------------------------------------------------------------------------
# Non-project-scoped chat endpoints
# ---------------------------------------------------------------------------

@starters_router.get("/starters")
async def get_starters(
    _key: str = Depends(verify_api_key),
) -> List[dict]:
    """Return grouped strategic conversation starters for the Co-Founder AI."""
    return STRATEGIC_STARTERS


@starters_router.get("/advisors", response_model=List[AdvisorInfo])
async def get_advisors(
    _key: str = Depends(verify_api_key),
) -> List[dict]:
    """Return all advisor configs (no system prompts) for the frontend advisor picker."""
    return get_advisor_info_list()
```

- [ ] **Step 2: Verify endpoints register**

```bash
docker compose up --build -d backend && sleep 3 && curl -s http://localhost:8989/openapi.json | python3 -m json.tool | grep -E "advisors|roundtable"
```

---

## Task 5: Frontend Types + API

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Update ChatMessage and ChatSendRequest types, add new types**

In `frontend/lib/types.ts`, replace the existing chat interfaces (lines 348-367) with:

```typescript
export interface ChatMessage {
  id: string;
  project_id: string;
  role: 'user' | 'assistant';
  content: string;
  metadata_?: Record<string, unknown> | null;
  created_at: string;
  advisor_id?: string | null;
  advisor_name?: string | null;
}

export interface ChatSendRequest {
  message: string;
  advisor_id?: string | null;
  include_workspace?: boolean;
  include_memory?: boolean;
  include_repo?: boolean;
}

export interface ChatRoundtableResponse {
  messages: ChatMessage[];
  routed_advisors: string[];
  roundtable_group: string;
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
  total: number;
}

export interface AdvisorInfo {
  id: string;
  name: string;
  tagline: string;
  expertise: string[];
  color: string;
  avatar: string;
}
```

- [ ] **Step 2: Update api.ts chat methods**

Replace the `chat` object in `frontend/lib/api.ts` (lines 483-498):

```typescript
export const chat = {
  send(projectId: string, data: ChatSendRequest): Promise<ChatRoundtableResponse> {
    return apiFetch<ChatRoundtableResponse>(`/projects/${projectId}/chat`, {
      method: 'POST', body: JSON.stringify(data),
    });
  },
  history(projectId: string, limit = 50): Promise<ChatHistoryResponse> {
    return apiFetch<ChatHistoryResponse>(`/projects/${projectId}/chat?limit=${limit}`);
  },
  clear(projectId: string): Promise<void> {
    return apiFetch(`/projects/${projectId}/chat`, { method: 'DELETE' });
  },
  starters(): Promise<ChatStarterGroup[]> {
    return apiFetch<ChatStarterGroup[]>('/chat/starters');
  },
  advisors(): Promise<AdvisorInfo[]> {
    return apiFetch<AdvisorInfo[]>('/chat/advisors');
  },
};
```

Also add `AdvisorInfo` and `ChatRoundtableResponse` to the import block at the top of api.ts from `./types`.

---

## Task 6: Frontend Advisor Registry

**Files:**
- Create: `frontend/lib/advisors.ts`

- [ ] **Step 1: Create frontend advisor registry**

```typescript
export interface AdvisorInfo {
  id: string;
  name: string;
  tagline: string;
  expertise: string[];
  color: string;
  avatar: string;
}

export const ADVISORS: Record<string, AdvisorInfo> = {
  yc_partner: {
    id: "yc_partner",
    name: "YC Partner",
    tagline: "Startup Strategy & PMF",
    expertise: ["startup", "pmf", "fundraising", "metrics", "pitch"],
    color: "#F59E0B",
    avatar: "/avatars/yc_partner.png",
  },
  elon_musk: {
    id: "elon_musk",
    name: "Elon Musk",
    tagline: "First Principles & Moonshots",
    expertise: ["scaling", "engineering", "vision", "first-principles", "moonshot"],
    color: "#3B82F6",
    avatar: "/avatars/elon_musk.png",
  },
  alex_hormozi: {
    id: "alex_hormozi",
    name: "Alex Hormozi",
    tagline: "$100M Offers & Value",
    expertise: ["pricing", "monetization", "offers", "leads", "sales"],
    color: "#10B981",
    avatar: "/avatars/alex_hormozi.png",
  },
  greg_isenberg: {
    id: "greg_isenberg",
    name: "Greg Isenberg",
    tagline: "Community-Led Growth",
    expertise: ["community", "social", "audience", "virality", "retention"],
    color: "#8B5CF6",
    avatar: "/avatars/greg_isenberg.png",
  },
  nathan_gotch: {
    id: "nathan_gotch",
    name: "Nathan Gotch",
    tagline: "SEO & Organic Growth",
    expertise: ["seo", "traffic", "organic-growth", "keywords", "content-marketing"],
    color: "#EC4899",
    avatar: "/avatars/nathan_gotch.png",
  },
  julia_mccoy: {
    id: "julia_mccoy",
    name: "Julia McCoy",
    tagline: "AI Content Strategy",
    expertise: ["content", "branding", "ai-content", "writing", "marketing"],
    color: "#F97316",
    avatar: "/avatars/julia_mccoy.png",
  },
  growth_tribe: {
    id: "growth_tribe",
    name: "Growth Tribe",
    tagline: "Growth Hacking & Experiments",
    expertise: ["growth-hacking", "experiments", "analytics", "activation", "retention"],
    color: "#06B6D4",
    avatar: "/avatars/growth_tribe.png",
  },
  dan_koe: {
    id: "dan_koe",
    name: "Dan Koe",
    tagline: "One-Person Business",
    expertise: ["solopreneur", "leverage", "digital-products", "personal-brand", "focus"],
    color: "#EF4444",
    avatar: "/avatars/dan_koe.png",
  },
};

export const ADVISOR_ORDER = [
  "yc_partner", "elon_musk", "alex_hormozi", "greg_isenberg",
  "nathan_gotch", "julia_mccoy", "growth_tribe", "dan_koe",
];
```

---

## Task 7: Placeholder Avatar Images

**Files:**
- Create: 8 SVG files in `frontend/public/avatars/`

- [ ] **Step 1: Create placeholder avatar SVGs**

Generate 8 simple placeholder SVGs using the advisor's initials and color. Each file is a 256x256 SVG with colored circle + white initials.

Create each file at `frontend/public/avatars/{id}.png` (actually SVG content saved as .png extension won't work — use .svg):

Actually, for simplicity and Next.js `<Image>` compatibility, create proper SVG files at `frontend/public/avatars/{id}.svg` and update the avatar paths in both registries to use `.svg`.

For each advisor, create `frontend/public/avatars/{id}.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <circle cx="128" cy="128" r="128" fill="{color}"/>
  <text x="128" y="140" text-anchor="middle" font-family="system-ui, sans-serif" font-size="80" font-weight="700" fill="white">{initials}</text>
</svg>
```

| File | Color | Initials |
|------|-------|----------|
| `yc_partner.svg` | `#F59E0B` | `YC` |
| `elon_musk.svg` | `#3B82F6` | `EM` |
| `alex_hormozi.svg` | `#10B981` | `AH` |
| `greg_isenberg.svg` | `#8B5CF6` | `GI` |
| `nathan_gotch.svg` | `#EC4899` | `NG` |
| `julia_mccoy.svg` | `#F97316` | `JM` |
| `growth_tribe.svg` | `#06B6D4` | `GT` |
| `dan_koe.svg` | `#EF4444` | `DK` |

Update the avatar paths in `backend/app/services/advisors.py` and `frontend/lib/advisors.ts` to use `.svg` extension.

---

## Task 8: AdvisorCard Component

**Files:**
- Create: `frontend/components/chat/AdvisorCard.tsx`

- [ ] **Step 1: Create the reusable advisor card component**

```tsx
"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";
import type { AdvisorInfo } from "@/lib/advisors";

interface AdvisorCardProps {
  advisor: AdvisorInfo;
  size: "sm" | "lg";
  selected?: boolean;
  onClick?: () => void;
}

export function AdvisorCard({ advisor, size, selected, onClick }: AdvisorCardProps) {
  if (size === "sm") {
    return (
      <div className="flex items-center gap-2">
        <div
          className="shrink-0 rounded-full overflow-hidden border-2"
          style={{ borderColor: advisor.color }}
        >
          <Image
            src={advisor.avatar}
            alt={advisor.name}
            width={28}
            height={28}
            className="rounded-full"
          />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold truncate" style={{ color: advisor.color }}>
            {advisor.name}
          </p>
          <p className="text-[10px] text-muted-foreground truncate">{advisor.tagline}</p>
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex flex-col items-center gap-1.5 px-3 py-2.5 rounded-lg border transition-all text-center shrink-0",
        "hover:bg-secondary/50",
        selected
          ? "border-2 bg-secondary/30"
          : "border-border",
      )}
      style={selected ? { borderColor: advisor.color } : undefined}
    >
      <div
        className="rounded-full overflow-hidden border-2"
        style={{ borderColor: advisor.color }}
      >
        <Image
          src={advisor.avatar}
          alt={advisor.name}
          width={48}
          height={48}
          className="rounded-full"
        />
      </div>
      <p className="text-xs font-semibold truncate max-w-[80px]">{advisor.name}</p>
      <p className="text-[9px] text-muted-foreground truncate max-w-[80px]">{advisor.tagline}</p>
    </button>
  );
}
```

---

## Task 9: RoundtableGroup Component

**Files:**
- Create: `frontend/components/chat/RoundtableGroup.tsx`

- [ ] **Step 1: Create the roundtable group wrapper**

```tsx
"use client";

import Image from "next/image";
import { ADVISORS } from "@/lib/advisors";
import { ChatMessage } from "@/components/chat/ChatMessage";
import type { ChatMessage as ChatMessageType } from "@/lib/types";
import { Users } from "lucide-react";

interface RoundtableGroupProps {
  messages: ChatMessageType[];
  roundtableGroup: string;
}

export function RoundtableGroup({ messages, roundtableGroup }: RoundtableGroupProps) {
  // Extract advisor IDs from the messages
  const advisorIds = messages
    .map((m) => m.advisor_id)
    .filter((id): id is string => !!id);

  return (
    <div className="space-y-3">
      {/* Roundtable header */}
      <div className="flex items-center gap-2 px-1">
        <Users className="w-3.5 h-3.5 text-muted-foreground" />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Roundtable
        </span>
        <div className="flex -space-x-1.5">
          {advisorIds.map((id) => {
            const advisor = ADVISORS[id];
            if (!advisor) return null;
            return (
              <div
                key={id}
                className="w-5 h-5 rounded-full overflow-hidden border border-background"
                title={advisor.name}
              >
                <Image
                  src={advisor.avatar}
                  alt={advisor.name}
                  width={20}
                  height={20}
                />
              </div>
            );
          })}
        </div>
        <span className="text-[10px] text-muted-foreground">
          {advisorIds.length} advisors weighed in
        </span>
      </div>

      {/* Advisor messages */}
      <div className="space-y-3 border-l-2 border-border/50 pl-3 ml-1">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
      </div>
    </div>
  );
}
```

---

## Task 10: ChatMessage — Advisor Badge

**Files:**
- Modify: `frontend/components/chat/ChatMessage.tsx`

- [ ] **Step 1: Add advisor badge to assistant messages**

Replace the full content of `frontend/components/chat/ChatMessage.tsx`:

```tsx
"use client";

import Image from "next/image";
import { formatDistanceToNow } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { ADVISORS } from "@/lib/advisors";
import type { ChatMessage as ChatMessageType } from "@/lib/types";

interface ChatMessageProps {
  message: ChatMessageType;
}

function markdownToHtml(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre class="chat-code-block"><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br />');
  return html;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const advisorId = message.advisor_id || message.metadata_?.advisor_id as string | undefined;
  const advisor = advisorId ? ADVISORS[advisorId] : null;

  return (
    <div
      className={cn(
        "flex flex-col gap-1 animate-in fade-in-0 slide-in-from-bottom-2 duration-200",
        isUser ? "items-end" : "items-start",
      )}
    >
      {/* Role label + timestamp */}
      <div className={cn("flex items-center gap-2 px-1", isUser ? "flex-row-reverse" : "flex-row")}>
        {/* Advisor avatar + name */}
        {advisor && !isUser ? (
          <div className="flex items-center gap-1.5">
            <div
              className="w-5 h-5 rounded-full overflow-hidden border"
              style={{ borderColor: advisor.color }}
            >
              <Image
                src={advisor.avatar}
                alt={advisor.name}
                width={20}
                height={20}
                className="rounded-full"
              />
            </div>
            <span className="text-xs font-semibold" style={{ color: advisor.color }}>
              {advisor.name}
            </span>
          </div>
        ) : (
          <span className="text-xs font-medium text-muted-foreground">
            {isUser ? "You" : "Co-Founder AI"}
          </span>
        )}
        <span className="text-xs text-muted-foreground/60">
          {formatDistanceToNow(message.created_at)}
        </span>
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-primary/15 text-foreground border border-primary/25 rounded-br-sm shadow-sm"
            : "bg-card text-foreground border rounded-bl-sm",
        )}
        style={
          advisor && !isUser
            ? { borderColor: `${advisor.color}30`, borderLeftWidth: "3px", borderLeftColor: advisor.color }
            : { borderColor: "var(--border)" }
        }
      >
        {isUser ? (
          <span className="whitespace-pre-wrap break-words">{message.content}</span>
        ) : (
          <div
            className="chat-prose break-words"
            dangerouslySetInnerHTML={{ __html: markdownToHtml(message.content) }}
          />
        )}
      </div>
    </div>
  );
}
```

---

## Task 11: ChatWindow — Advisor Picker + Roundtable Grouping

**Files:**
- Modify: `frontend/components/chat/ChatWindow.tsx`

This is the largest frontend change. Key modifications:
1. Add advisor picker bar above the input area
2. Update `handleSend` to handle `ChatRoundtableResponse`
3. Group history messages by `roundtable_group` for rendering

- [ ] **Step 1: Add imports and state**

Add to the import block at the top:

```typescript
import { AdvisorCard } from "@/components/chat/AdvisorCard";
import { RoundtableGroup } from "@/components/chat/RoundtableGroup";
import { ADVISORS, ADVISOR_ORDER } from "@/lib/advisors";
import type { ChatRoundtableResponse, AdvisorInfo } from "@/lib/types";
import { Users } from "lucide-react";
```

Add to state declarations (after `includeRepo` state):

```typescript
  // Advisor selection — null means roundtable (default)
  const [selectedAdvisor, setSelectedAdvisor] = useState<string | null>(null);
```

- [ ] **Step 2: Update handleSend to handle roundtable response**

Replace the try block inside `handleSend` (the `chatApi.send(...)` call and success handling):

```typescript
    try {
      const res = await chatApi.send(projectId, {
        message: messageText,
        advisor_id: selectedAdvisor || undefined,
        include_workspace: includeWorkspace,
        include_memory: includeMemory,
        include_repo: includeRepo,
      });

      // Refresh the full history from the server
      await mutate();
      setOptimisticMessages([]);
    } catch (err) {
```

- [ ] **Step 3: Add message grouping logic**

Add this helper function before the `return` statement:

```typescript
  // Group consecutive assistant messages by roundtable_group for rendering
  function groupMessages(msgs: ChatMessageType[]) {
    const groups: Array<{ type: "single"; message: ChatMessageType } | { type: "roundtable"; messages: ChatMessageType[]; group: string }> = [];
    let i = 0;
    while (i < msgs.length) {
      const msg = msgs[i];
      const group = msg.metadata_?.roundtable_group as string | undefined;

      if (msg.role === "assistant" && group) {
        // Collect all messages with the same roundtable_group
        const roundtableMessages: ChatMessageType[] = [msg];
        while (i + 1 < msgs.length && msgs[i + 1].metadata_?.roundtable_group === group) {
          i++;
          roundtableMessages.push(msgs[i]);
        }
        if (roundtableMessages.length > 1) {
          groups.push({ type: "roundtable", messages: roundtableMessages, group });
        } else {
          groups.push({ type: "single", message: msg });
        }
      } else {
        groups.push({ type: "single", message: msg });
      }
      i++;
    }
    return groups;
  }
```

- [ ] **Step 4: Update the message list rendering**

Replace the message rendering section (the `displayMessages.map(...)` block inside the JSX, approximately the `<>` block with `displayMessages.map`) with:

```tsx
          <>
            {groupMessages(displayMessages).map((item, idx) =>
              item.type === "roundtable" ? (
                <RoundtableGroup
                  key={item.group}
                  messages={item.messages}
                  roundtableGroup={item.group}
                />
              ) : (
                <ChatMessage key={item.message.id} message={item.message} />
              ),
            )}
            {isSending && <TypingIndicator />}
          </>
```

- [ ] **Step 5: Add advisor picker bar**

Add the advisor picker bar above the context toggles in the input area. Insert this JSX right before the `{/* Context toggles */}` comment:

```tsx
        {/* Advisor picker */}
        <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-thin">
          <button
            type="button"
            onClick={() => setSelectedAdvisor(null)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 rounded-lg border transition-all shrink-0 text-xs font-medium",
              selectedAdvisor === null
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:border-primary/30",
            )}
          >
            <Users className="w-3.5 h-3.5" />
            Roundtable
          </button>
          {ADVISOR_ORDER.map((id) => {
            const advisor = ADVISORS[id];
            if (!advisor) return null;
            return (
              <AdvisorCard
                key={id}
                advisor={advisor}
                size="lg"
                selected={selectedAdvisor === id}
                onClick={() => setSelectedAdvisor(selectedAdvisor === id ? null : id)}
              />
            );
          })}
        </div>
```

- [ ] **Step 6: Update the header badge**

Replace the YC-style badge in the header (the `<div>` with `GraduationCap` icon, around line 235):

```tsx
        <div className="flex items-center gap-2.5">
          <MessageSquare className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Co-Founder AI</span>
          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 border border-primary/25 text-primary">
            <Users className="w-3 h-3" />
            <span className="text-[10px] font-semibold tracking-wide uppercase">Roundtable</span>
          </div>
        </div>
```

- [ ] **Step 7: Update the empty state**

Replace the empty state icon and text (the `GraduationCap` div and description):

```tsx
            <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Users className="w-7 h-7 text-primary" />
            </div>
            <div className="text-center space-y-1">
              <p className="text-sm font-medium">Your co-founder roundtable is ready</p>
              <p className="text-xs text-muted-foreground">
                Ask anything — 3-4 advisors will weigh in from different perspectives, grounded in your actual project data.
              </p>
            </div>
```

---

## Task 12: Integration Verification

- [ ] **Step 1: Rebuild and verify backend starts**

```bash
docker compose up --build -d backend && sleep 5 && docker compose logs backend --tail 10
```

- [ ] **Step 2: Verify advisor endpoint**

```bash
curl -s http://localhost:8989/chat/advisors -H "X-API-Key: ..." | python3 -m json.tool | head -20
```
Expected: JSON array of 8 advisor objects.

- [ ] **Step 3: Verify frontend builds**

```bash
cd frontend && npm run build
```
Expected: Build succeeds with no type errors.

- [ ] **Step 4: Verify advisor picker renders**

Open the chat page in browser. The advisor picker bar should appear above the input with 8 advisor cards and a "Roundtable" button.

---

## Summary

| Task | Component | Files | Complexity |
|------|-----------|-------|-----------|
| 1 | Advisor Registry | Create: `advisors.py` | High (600+ lines of prompts) |
| 2 | Backend Schemas | Modify: `schemas/chat.py` | Low |
| 3 | Chat Service | Modify: `chat_service.py` | High (core logic) |
| 4 | Chat Router | Modify: `routers/chat.py` | Medium |
| 5 | Frontend Types + API | Modify: `types.ts`, `api.ts` | Low |
| 6 | Frontend Advisor Registry | Create: `advisors.ts` | Low |
| 7 | Placeholder Avatars | Create: 8 SVG files | Low |
| 8 | AdvisorCard Component | Create: `AdvisorCard.tsx` | Low |
| 9 | RoundtableGroup Component | Create: `RoundtableGroup.tsx` | Low |
| 10 | ChatMessage Update | Modify: `ChatMessage.tsx` | Medium |
| 11 | ChatWindow Update | Modify: `ChatWindow.tsx` | High (biggest frontend change) |
| 12 | Integration Verification | Verification only | Low |

Total: 4 new backend/frontend code files, 8 SVG assets, 6 modified files.
