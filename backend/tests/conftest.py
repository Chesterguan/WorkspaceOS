"""
Pytest fixtures for ProjectScribe API integration tests.

Pure HTTP tests against the running Docker backend.
No app imports — avoids DB connection pool conflicts.
Requires: docker compose up -d backend (server must be running)
"""
import asyncio
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("TEST_API_KEY", "dev-secret-key")
API_HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async HTTP client that talks to the running backend."""
    async with AsyncClient(base_url=BASE_URL, timeout=60.0) as ac:
        yield ac


# ---------------------------------------------------------------------------
# DB-level fixtures for unit/integration tests that need direct DB access.
# Used by test_knowledge_extractor.py and any future direct-DB tests.
# ---------------------------------------------------------------------------

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.project import Project


@pytest_asyncio.fixture
async def db_session():
    """Async SQLAlchemy session for direct-DB tests.

    NOTE: The savepoint / begin_nested pattern does not work with SQLAlchemy's
    AsyncSession when the SUT calls session.commit() — the async commit() releases
    the outer transaction rather than just the SAVEPOINT, making the teardown
    rollback a no-op.  Row cleanup is instead driven by sample_user teardown,
    which deletes the user row and lets FK CASCADE handle everything downstream.

    pool_dispose=True: after SUT code commits its own transaction the asyncpg
    pool can hold connections in a half-open state.  Disposing after each
    function-scoped session guarantees the next test starts with a fresh pool.
    """
    from app.database import engine
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass
    # Dispose pool connections so the next function-scoped test starts fresh.
    # This is safe: dispose() closes idle connections; active ones are returned
    # to a new pool on their next checkin.
    try:
        await engine.dispose()
    except Exception:
        pass


@pytest_asyncio.fixture
async def sample_user(db_session):
    """A minimal User row scoped to a single test.

    Teardown deletes the user (and all cascade-linked rows: projects,
    chat_messages, knowledge_nodes, knowledge_edges) so that repeated
    test runs do not accumulate rows in the DB.
    """
    u = User(email=f"test+knowledge+{__import__('uuid').uuid4().hex[:8]}@example.com")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    user_id = u.id
    try:
        yield u
    finally:
        # Use a fresh session for cleanup so a poisoned test session doesn't
        # prevent deletion.
        async with AsyncSessionLocal() as cleanup:
            from sqlalchemy import delete
            from app.models.user import User as _User
            await cleanup.execute(delete(_User).where(_User.id == user_id))
            await cleanup.commit()


@pytest_asyncio.fixture
async def sample_project(db_session, sample_user):
    """A minimal Project row owned by sample_user."""
    import uuid as _uuid
    slug = f"testproj-{_uuid.uuid4().hex[:8]}"
    p = Project(name="TestProj", slug=slug, user_id=sample_user.id)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p
