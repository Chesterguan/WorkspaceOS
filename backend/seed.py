"""
Seed script — populates the database with realistic demo data.

Usage:
    cd backend
    SEED_DEMO_DATA=true python seed.py

Demo seeding is opt-in: set SEED_DEMO_DATA=true (or 1/yes) to populate the
demo user + projects + drafts. Without the env var, the script is a no-op
so fresh deployments boot into an empty DB ready for real registration.

Requires the database to already have the schema applied (alembic upgrade head).
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.draft import Draft
from app.models.memory import MemoryEntry
from app.models.narrative import Narrative
from app.models.project import Project
from app.models.user import User


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_or_create_user(db: AsyncSession, email: str, display_name: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email, display_name=display_name)
        db.add(user)
        await db.flush()

    # Set a default password for the demo user if none exists
    if not user.password_hash:
        from app.services.auth_service import hash_password

        user.password_hash = hash_password("demo123")
        await db.flush()

    return user


async def _get_or_create_project(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    slug: str,
    description: str,
    github_repo: str,
) -> Project:
    result = await db.execute(
        select(Project).where(Project.user_id == user_id, Project.slug == slug)
    )
    project = result.scalar_one_or_none()
    if project is None:
        project = Project(
            user_id=user_id,
            name=name,
            slug=slug,
            description=description,
            github_repo=github_repo,
            github_branch="main",
            status="active",
        )
        db.add(project)
        await db.flush()
    return project


# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------

async def seed() -> None:
    if os.getenv("SEED_DEMO_DATA", "").lower() not in ("1", "true", "yes"):
        print("Seed skipped: SEED_DEMO_DATA not enabled "
              "(set SEED_DEMO_DATA=true to populate demo user + projects).")
        return

    async with AsyncSessionLocal() as db:
        # Idempotency guard: skip seeding entirely if the DB already has real
        # users. Once the demo account has been renamed / merged into a real
        # account, re-creating a fresh "demo@prsecretary.dev" row on every
        # container restart would silently fork project ownership and leak
        # seed projects onto a parallel account. Only seed on a truly empty DB.
        existing_count_result = await db.execute(
            text("SELECT COUNT(*) FROM users")
        )
        existing_count = existing_count_result.scalar_one()
        if existing_count and existing_count > 0:
            print(f"Seed skipped: {existing_count} user(s) already exist.")
            return

        # ------------------------------------------------------------------
        # 1. Demo user
        # ------------------------------------------------------------------
        user = await _get_or_create_user(
            db,
            email="demo@prsecretary.dev",
            display_name="Demo User",
        )
        print(f"User: {user.email} ({user.id})")

        # ------------------------------------------------------------------
        # 2. Project: ProjectScribe
        # ------------------------------------------------------------------
        scribe = await _get_or_create_project(
            db,
            user_id=user.id,
            name="ProjectScribe",
            slug="project-scribe",
            description=(
                "AI co-founder platform — syncs GitHub activity, generates content, "
                "writes papers, manages memory with hybrid RAG, and provides strategic advice."
            ),
            github_repo="acme/project-scribe",
        )
        print(f"Project: {scribe.name} ({scribe.id})")

        # Narrative for ProjectScribe
        result = await db.execute(
            select(Narrative).where(Narrative.project_id == scribe.id)
        )
        if result.scalar_one_or_none() is None:
            scribe_narrative = Narrative(
                project_id=scribe.id,
                one_liner=(
                    "ProjectScribe watches your commits and writes your LinkedIn posts, "
                    "tweets, and release notes — automatically."
                ),
                target_audience=(
                    "Indie hackers, solo founders, and small engineering teams who ship "
                    "constantly but never have time to talk about it publicly."
                ),
                origin_story=(
                    "I spent three months building a side project and only told two people. "
                    "Every week I'd think 'I should post about this' and never did. "
                    "ProjectScribe is the tool I wish I had."
                ),
                preferred_angles=[
                    "developer productivity",
                    "async content creation",
                    "shipping velocity without losing your audience",
                    "the invisible builder problem",
                ],
                avoided_angles=[
                    "AI replacing writers",
                    "automated spam",
                    "set-and-forget marketing",
                ],
                faq=[
                    {
                        "q": "Does it post automatically?",
                        "a": "No — it drafts, you approve. You're always in the loop.",
                    },
                    {
                        "q": "Which platforms does it support?",
                        "a": "LinkedIn, Twitter/X, Xiaohongshu, Medium outlines, and GitHub Releases.",
                    },
                    {
                        "q": "Do I need to connect my social accounts?",
                        "a": "Not yet. Right now you copy-paste the drafts. Native publishing is on the roadmap.",
                    },
                ],
                tone_notes=(
                    "Conversational and honest. We're builders talking to builders. "
                    "No hype, no buzzwords. Concrete examples over abstract benefits."
                ),
            )
            db.add(scribe_narrative)
            await db.flush()
            print(f"  Narrative created for {scribe.name}")

        # ------------------------------------------------------------------
        # 3. Project: FastCache
        # ------------------------------------------------------------------
        fastcache = await _get_or_create_project(
            db,
            user_id=user.id,
            name="FastCache",
            slug="fastcache",
            description=(
                "A zero-config in-process cache for Python async applications. "
                "Drop-in TTL cache with LRU eviction and optional Redis persistence."
            ),
            github_repo="acme/fastcache",
        )
        print(f"Project: {fastcache.name} ({fastcache.id})")

        result = await db.execute(
            select(Narrative).where(Narrative.project_id == fastcache.id)
        )
        if result.scalar_one_or_none() is None:
            fastcache_narrative = Narrative(
                project_id=fastcache.id,
                one_liner=(
                    "FastCache gives your async Python app an LRU cache with TTL in "
                    "one decorator, with optional Redis persistence and zero config."
                ),
                target_audience=(
                    "Python backend developers building FastAPI, Starlette, or asyncio "
                    "services who want a caching layer without the operational overhead "
                    "of a standalone Redis deployment for development."
                ),
                origin_story=(
                    "While building a FastAPI service I added Redis for caching and spent "
                    "two days fighting connection pool edge cases in tests. I wanted "
                    "something that just worked locally and could swap in Redis for prod."
                ),
                preferred_angles=[
                    "zero config, sane defaults",
                    "developer experience over raw performance",
                    "progressive complexity — simple by default, powerful when needed",
                ],
                avoided_angles=[
                    "claiming to be faster than Redis",
                    "enterprise caching infrastructure",
                ],
                faq=[
                    {
                        "q": "Is this thread-safe?",
                        "a": "Yes — it uses asyncio locks internally to prevent cache stampedes.",
                    },
                    {
                        "q": "Can I use it in production?",
                        "a": "For moderate workloads, yes. For high-throughput production use, pair it with the Redis backend.",
                    },
                ],
                tone_notes=(
                    "Technical and direct. The audience is experienced Python devs — "
                    "respect their time, show code examples early, explain the trade-offs honestly."
                ),
            )
            db.add(fastcache_narrative)
            await db.flush()
            print(f"  Narrative created for {fastcache.name}")

        # ------------------------------------------------------------------
        # 4. Memory entries (no embeddings — seeded without API calls)
        # ------------------------------------------------------------------
        memory_seeds = [
            # ProjectScribe
            (
                scribe.id,
                "narrative_fact",
                "ProjectScribe was first shown publicly at an indie hacker meetup in March 2026 "
                "to a room of 40 people. 12 signed up for the waitlist on the spot.",
                "manual",
            ),
            (
                scribe.id,
                "user_annotation",
                "Users consistently mention that the LinkedIn drafts feel 'too polished'. "
                "They want something that sounds more like them, less like a press release. "
                "Tune the LinkedIn template tone down.",
                "user-feedback-2026-03-15",
            ),
            (
                scribe.id,
                "commit_summary",
                "Added pgvector-based semantic search to memory retrieval (March 2026). "
                "This allows the AI to pull the most contextually relevant past facts "
                "rather than just the most recent ones.",
                "sha:a3f7c21",
            ),
            # FastCache
            (
                fastcache.id,
                "narrative_fact",
                "FastCache reached 500 GitHub stars in its first month after being featured "
                "in the Python Weekly newsletter (issue #591).",
                "manual",
            ),
            (
                fastcache.id,
                "release_note",
                "v0.3.0 introduced the Redis persistence backend. Migration from the in-process "
                "backend requires only a one-line config change.",
                "tag:v0.3.0",
            ),
            (
                fastcache.id,
                "user_annotation",
                "Three users have reported that the LRU eviction under high concurrency can "
                "cause a brief performance dip. Investigate asyncio lock contention. "
                "Mentioned in GitHub issues #34, #41, #55.",
                "github-issues",
            ),
        ]

        for proj_id, etype, content, source_ref in memory_seeds:
            # Check for duplicates by content prefix to keep seed idempotent
            existing = await db.execute(
                select(MemoryEntry).where(
                    MemoryEntry.project_id == proj_id,
                    MemoryEntry.source_ref == source_ref,
                )
            )
            if existing.scalar_one_or_none() is None:
                entry = MemoryEntry(
                    project_id=proj_id,
                    entry_type=etype,
                    content=content,
                    source_ref=source_ref,
                    # No embedding — would require a live OpenAI key.
                    # Run `python -c "from app.services.memory_service import add_entry; ..."` to embed.
                    embedding=None,
                )
                db.add(entry)
        await db.flush()
        print(f"  Memory entries seeded")

        # ------------------------------------------------------------------
        # 5. Sample drafts
        # ------------------------------------------------------------------
        draft_seeds = [
            (
                scribe.id,
                "linkedin",
                "ProjectScribe v0.1: From 0 to draft in 30 seconds",
                """Most indie hackers I know have the same problem: they ship every week but their LinkedIn is a graveyard.

Not because they don't want to share — they do. They just can't context-switch from "build mode" to "marketing mode" 6 times a week.

I built ProjectScribe to fix this for myself.

It watches your GitHub commits and releases, learns your project's story (your narrative, your audience, your voice), and drafts platform-specific posts ready for your review.

You connect GitHub → fill in a one-liner and audience description → push commits as normal.

Within 30 seconds of syncing, you have a LinkedIn post, a Twitter thread, and release notes — all in draft, waiting for your approval.

No auto-posting. You stay in control.

Still rough around the edges (it's v0.1), but the core loop works. I've been using it for 3 weeks and my posting frequency went from 0 to roughly 3x/week.

If you ship side projects and hate writing about them, give it a try: [link in bio]

#indieHacker #buildinpublic #developertools #AI #productivity""",
                "draft",
            ),
            (
                scribe.id,
                "twitter",
                None,
                """1/ Most indie hackers ship weekly but post monthly (if that).

Not laziness — context switching from code to marketing is exhausting.

I built a fix: ProjectScribe 🧵

2/ It watches your GitHub commits + releases, learns your project's voice, and drafts posts for every platform.

LinkedIn, Twitter, Xiaohongshu, Medium outlines, release notes — all from your commit history.

3/ The flow:
→ Connect GitHub repo
→ Write a one-liner + audience description
→ Ship as normal
→ ProjectScribe drafts, you approve

No auto-posting. You're always the author.

4/ Under the hood:
- pgvector for semantic memory (it remembers past angles you liked)
- FastAPI + async SQLAlchemy
- Pluggable AI: OpenAI or Anthropic

5/ I've been dogfooding it for 3 weeks.

Before: 0 posts/week
After: ~3 posts/week — all reviewed and customised, none from scratch

6/ v0.1 is rough. Rate limits, no mobile app, copy-paste workflow.

But the core loop works and I'm validating before over-engineering.

7/ If you're a builder who hates marketing yourself — does this scratch your itch?

Would love brutal feedback. DMs open.""",
                "approved",
            ),
            (
                fastcache.id,
                "github_release",
                "FastCache v0.3.0",
                """## What's new in v0.3.0

This release adds the long-requested Redis persistence backend, making FastCache usable as a shared cache across multiple process instances or worker replicas.

### What's New

- **Redis backend** (`fastcache.backends.RedisBackend`) — persistent, shared cache with the same decorator API as the in-process backend.
- **Async connection pooling** — the Redis backend uses `redis.asyncio` with configurable pool size (default: 10).
- **Serialization hooks** — pass a custom `serializer` / `deserializer` pair for non-JSON-serializable values.
- **Backend auto-detection** — if a `FASTCACHE_REDIS_URL` env var is set, the Redis backend is used automatically.

### Bug Fixes

- Fixed a race condition in LRU eviction under high concurrency (#34, #41, #55) — eviction now uses an `asyncio.Lock` per cache key rather than a global lock, reducing contention by ~60% in benchmarks.
- `@cache` decorator now correctly propagates type hints from the wrapped function.

### Breaking Changes

None. Existing in-process usage is unchanged.

### Full Changelog

https://github.com/acme/fastcache/compare/v0.2.1...v0.3.0""",
                "approved",
            ),
            (
                fastcache.id,
                "medium_outline",
                "Stop Fighting Redis in Development: How FastCache Gives You Caching Without the Ops Overhead",
                """# Article Outline

**Title:** Stop Fighting Redis in Development: How FastCache Gives You Caching Without the Ops Overhead

**Subtitle:** A practical guide to zero-config async caching in Python — and when you actually need Redis

---

## Intro
- The Redis setup tax: every FastAPI project eventually adds caching, and every time you configure Redis, write connection pool boilerplate, and debug Docker Compose.
- FastCache's premise: dev-friendly in-process cache by default, Redis in production when you're ready.
- What this article covers: the design choices, how to use it, and when *not* to use it.

---

## 1. Why In-Process Caching Gets a Bad Rap
- Legitimate concerns: cache not shared across workers, lost on restart.
- When it's completely fine: single-worker dev servers, lambda-style functions, read-heavy GET endpoints.
- The 80/20 rule: most apps don't need distributed cache until they have distributed load.

## 2. FastCache in 5 Minutes
- Installation and first decorator.
- TTL, LRU eviction, and async safety.
- Code example: caching a database query in a FastAPI route.

## 3. Under the Hood: Async LRU with TTL
- How the `asyncio.Lock` per-key design prevents stampedes.
- Memory accounting and eviction policy.
- Benchmark: vs. functools.lru_cache and aiocache.

## 4. Graduating to Redis: One Config Change
- The `FASTCACHE_REDIS_URL` env var.
- What changes (persistence, shared state) and what doesn't (decorator API).
- Connection pool sizing for production.

## 5. When FastCache Is the Wrong Tool
- Multi-region deployments: use Redis Cluster.
- Session storage: use a proper session backend.
- Pub/sub or streams: FastCache is a cache, not a message broker.

---

## Conclusion
- The key insight: start simple, swap when you need to.
- Call to action: star the repo, open an issue with your use case.

**Suggested tags:** Python, FastAPI, Caching, Redis, AsyncIO, Backend Development""",
                "draft",
            ),
        ]

        for proj_id, platform, title, content, status in draft_seeds:
            # Idempotency: skip if a root draft with the same platform + title exists
            check_query = select(Draft).where(
                Draft.project_id == proj_id,
                Draft.platform == platform,
                Draft.parent_draft_id.is_(None),
            )
            if title:
                check_query = check_query.where(Draft.title == title)
            existing = await db.execute(check_query)
            if existing.scalar_one_or_none() is None:
                draft = Draft(
                    project_id=proj_id,
                    platform=platform,
                    title=title,
                    content=content,
                    status=status,
                    version=1,
                )
                db.add(draft)

        await db.flush()
        print(f"  Drafts seeded")

        await db.commit()
        print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
