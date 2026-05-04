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
    """Async SQLAlchemy session. Rolls back after each test to keep the DB clean."""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def sample_user(db_session):
    """A minimal User row scoped to a single test."""
    u = User(email=f"test+knowledge+{__import__('uuid').uuid4().hex[:8]}@example.com")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


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
