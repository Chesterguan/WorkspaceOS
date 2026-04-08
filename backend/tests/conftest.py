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
