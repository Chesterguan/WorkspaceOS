"""
Tests for the project activity feed.

All DB-touching tests go through HTTP — the backend opens a fresh
AsyncSession per request, so they sidestep the pooled-engine /
per-test-event-loop conflict that bites when you hit AsyncSessionLocal
directly from an asyncio_mode=auto test. Pure-logic bits
(source coercion, summary truncation) are unit-tested against an in-memory
fake session so they don't need a DB at all.
"""
import os
import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.services.activity_service import _SOURCES, log_event


BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
API_HEADERS = {"X-API-Key": os.environ.get("TEST_API_KEY", "dev-secret-key")}


# ---------- Pure-logic unit tests with a fake session -----------------------

class _FakeSession:
    """Records `.add()` and awaits `.flush()` like a real AsyncSession."""
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


async def test_log_event_coerces_unknown_source_to_system():
    db = _FakeSession()
    entry = await log_event(db, uuid.uuid4(), "x.y", "s", source="bogus")
    assert entry is not None
    assert entry.source == "system"
    assert "bogus" not in _SOURCES  # sanity: the coercion was real


async def test_log_event_truncates_oversized_summary():
    db = _FakeSession()
    entry = await log_event(db, uuid.uuid4(), "x.y", "x" * 800)
    assert entry is not None
    assert len(entry.summary) == 500


async def test_log_event_empty_summary_falls_back_to_placeholder():
    db = _FakeSession()
    entry = await log_event(db, uuid.uuid4(), "x.y", "   ")
    assert entry is not None
    assert entry.summary == "(no summary)"


async def test_log_event_swallows_db_failure():
    """A broken DB write must not bubble up — it would break real endpoints."""
    class _BrokenSession:
        def add(self, _obj):
            raise RuntimeError("database on fire")
        async def flush(self):
            return None
    result = await log_event(_BrokenSession(), uuid.uuid4(), "x", "y")
    assert result is None  # swallowed, not raised


# ---------- HTTP integration tests ------------------------------------------

async def test_patch_project_emits_activity_event():
    """PATCH a noteworthy field → feed shows a project.edited event."""
    slug = f"act-e2e-{uuid.uuid4().hex[:8]}"
    async with AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        create = await client.post(
            "/api/v1/projects",
            headers=API_HEADERS,
            json={"name": "Activity E2E", "slug": slug},
        )
        assert create.status_code == 201, create.text
        pid = create.json()["id"]

        try:
            patch = await client.patch(
                f"/api/v1/projects/{pid}",
                headers=API_HEADERS,
                json={"focus_notes": "ship the feed by EOD"},
            )
            assert patch.status_code == 200

            feed = await client.get(
                f"/api/v1/projects/{pid}/activity",
                headers=API_HEADERS,
            )
            assert feed.status_code == 200, feed.text
            body = feed.json()
            event_types = [e["event_type"] for e in body["items"]]
            assert "project.edited" in event_types
            edited = next(e for e in body["items"] if e["event_type"] == "project.edited")
            assert "focus_notes" in (edited.get("details") or {}).get("changed_fields", [])
        finally:
            await client.delete(
                f"/api/v1/projects/{pid}",
                headers=API_HEADERS,
            )


async def test_patch_trivial_field_does_not_emit():
    """Status/local_path edits are plumbing — feed should stay empty."""
    slug = f"act-trivial-{uuid.uuid4().hex[:8]}"
    async with AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        create = await client.post(
            "/api/v1/projects",
            headers=API_HEADERS,
            json={"name": "Trivial Edit", "slug": slug},
        )
        pid = create.json()["id"]
        try:
            await client.patch(
                f"/api/v1/projects/{pid}",
                headers=API_HEADERS,
                json={"status": "archived"},
            )
            feed = await client.get(
                f"/api/v1/projects/{pid}/activity",
                headers=API_HEADERS,
            )
            assert feed.status_code == 200
            event_types = [e["event_type"] for e in feed.json()["items"]]
            assert "project.edited" not in event_types
        finally:
            await client.delete(
                f"/api/v1/projects/{pid}",
                headers=API_HEADERS,
            )


async def test_feed_pagination_with_cursor():
    """Seed 3 edits via PATCH, page through with limit=2."""
    slug = f"act-page-{uuid.uuid4().hex[:8]}"
    async with AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        create = await client.post(
            "/api/v1/projects",
            headers=API_HEADERS,
            json={"name": "Pagination", "slug": slug},
        )
        pid = create.json()["id"]
        try:
            # Three noteworthy edits → three project.edited events
            for i in range(3):
                await client.patch(
                    f"/api/v1/projects/{pid}",
                    headers=API_HEADERS,
                    json={"description": f"v{i}"},
                )

            page1 = await client.get(
                f"/api/v1/projects/{pid}/activity",
                headers=API_HEADERS,
                params={"limit": 2},
            )
            assert page1.status_code == 200
            b1 = page1.json()
            assert len(b1["items"]) == 2
            assert b1["next_cursor"] is not None

            # Pass the cursor via params so httpx URL-encodes the "+" in the
            # ISO timezone — embedding it raw would decode to a space server-side.
            page2 = await client.get(
                f"/api/v1/projects/{pid}/activity",
                headers=API_HEADERS,
                params={"limit": 2, "cursor": b1["next_cursor"]},
            )
            assert page2.status_code == 200
            b2 = page2.json()
            assert len(b2["items"]) >= 1
            # No duplicates between pages
            ids1 = {e["id"] for e in b1["items"]}
            ids2 = {e["id"] for e in b2["items"]}
            assert ids1.isdisjoint(ids2)
        finally:
            await client.delete(
                f"/api/v1/projects/{pid}",
                headers=API_HEADERS,
            )
