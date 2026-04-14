"""
Tests for the Calendar skill: classifier fallback behaviour, Inbox
idempotency, and the /skills endpoints' basic contracts.

Classifier tests mock the AI client so the logic is exercised
deterministically without a real cloud call. Inbox idempotency goes
through the HTTP surface to avoid the pooled-engine / per-test-loop
conflict we hit earlier in test_activity.py.
"""
import os
import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.services import classifier_service


BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
API_HEADERS = {"X-API-Key": os.environ.get("TEST_API_KEY", "dev-secret-key")}


# ---------- classifier JSON extraction (pure) ------------------------------

def test_extract_json_plain():
    parsed = classifier_service._extract_json(
        '{"project_id": "abc", "confidence": 0.9, "reason": "matches"}'
    )
    assert parsed == {"project_id": "abc", "confidence": 0.9, "reason": "matches"}


def test_extract_json_with_code_fence():
    parsed = classifier_service._extract_json(
        'Sure thing:\n```json\n{"project_id": "x", "confidence": 0.8}\n```\n'
    )
    assert parsed == {"project_id": "x", "confidence": 0.8}


def test_extract_json_with_trailing_prose():
    parsed = classifier_service._extract_json(
        '{"project_id": "x", "confidence": 0.5}\n\nNote: just guessing.'
    )
    assert parsed == {"project_id": "x", "confidence": 0.5}


def test_extract_json_unparseable_returns_none():
    assert classifier_service._extract_json("no json at all") is None
    assert classifier_service._extract_json("{broken") is None


# ---------- classifier thresholding (with mocked AI) ----------------------

async def test_classifier_low_confidence_routes_to_inbox(monkeypatch):
    """Confidence below threshold → Classification with fallback_to_inbox=True."""
    user_id = uuid.uuid4()
    real_proj_id = uuid.uuid4()
    inbox_id = uuid.uuid4()

    # Catalogue has one real project the AI would pick.
    async def fake_catalogue(uid, db):
        return [{
            "project_id": str(real_proj_id),
            "name": "Real",
            "slug": "real",
            "description": "",
            "wiki_excerpt": "",
        }]
    monkeypatch.setattr(
        classifier_service, "_build_project_catalogue", fake_catalogue,
    )

    # Inbox fallback — return a SimpleNamespace that quacks like a Project.
    async def fake_get_inbox(uid, db):
        return SimpleNamespace(id=inbox_id)
    monkeypatch.setattr(
        classifier_service.inbox_service, "get_or_create_inbox", fake_get_inbox,
    )

    # AI picks the real project but flags very low confidence.
    class FakeAI:
        async def complete(self, system, user):
            return f'{{"project_id": "{real_proj_id}", "confidence": 0.3, "reason": "weak match"}}'
    monkeypatch.setattr(classifier_service, "get_cloud_client", lambda: FakeAI())

    result = await classifier_service.classify_into_project(
        content="any",
        user_id=user_id,
        db=None,  # not touched by the mocks
    )
    assert result.fallback_to_inbox is True
    assert result.project_id == inbox_id
    assert result.confidence == 0.3


async def test_classifier_high_confidence_picks_real_project(monkeypatch):
    user_id = uuid.uuid4()
    real_proj_id = uuid.uuid4()
    inbox_id = uuid.uuid4()

    async def fake_catalogue(uid, db):
        return [{
            "project_id": str(real_proj_id),
            "name": "Real", "slug": "real", "description": "", "wiki_excerpt": "",
        }]
    monkeypatch.setattr(classifier_service, "_build_project_catalogue", fake_catalogue)

    async def fake_get_inbox(uid, db):
        return SimpleNamespace(id=inbox_id)
    monkeypatch.setattr(classifier_service.inbox_service, "get_or_create_inbox", fake_get_inbox)

    class FakeAI:
        async def complete(self, system, user):
            return f'{{"project_id": "{real_proj_id}", "confidence": 0.85, "reason": "clear"}}'
    monkeypatch.setattr(classifier_service, "get_cloud_client", lambda: FakeAI())

    result = await classifier_service.classify_into_project("any", user_id, None)
    assert result.fallback_to_inbox is False
    assert result.project_id == real_proj_id
    assert result.confidence == 0.85


async def test_classifier_hallucinated_project_id_falls_to_inbox(monkeypatch):
    """If the AI returns a UUID that isn't in the user's catalogue we must
    not accept it — that would silently leak data across users."""
    user_id = uuid.uuid4()
    real_proj_id = uuid.uuid4()
    other_proj_id = uuid.uuid4()  # not in the catalogue
    inbox_id = uuid.uuid4()

    async def fake_catalogue(uid, db):
        return [{
            "project_id": str(real_proj_id),
            "name": "Real", "slug": "real", "description": "", "wiki_excerpt": "",
        }]
    monkeypatch.setattr(classifier_service, "_build_project_catalogue", fake_catalogue)

    async def fake_get_inbox(uid, db):
        return SimpleNamespace(id=inbox_id)
    monkeypatch.setattr(classifier_service.inbox_service, "get_or_create_inbox", fake_get_inbox)

    class FakeAI:
        async def complete(self, system, user):
            return f'{{"project_id": "{other_proj_id}", "confidence": 0.99, "reason": "x"}}'
    monkeypatch.setattr(classifier_service, "get_cloud_client", lambda: FakeAI())

    result = await classifier_service.classify_into_project("any", user_id, None)
    assert result.fallback_to_inbox is True
    assert result.project_id == inbox_id


async def test_classifier_no_projects_uses_inbox(monkeypatch):
    user_id = uuid.uuid4()
    inbox_id = uuid.uuid4()

    async def empty_catalogue(uid, db):
        return []
    monkeypatch.setattr(classifier_service, "_build_project_catalogue", empty_catalogue)

    async def fake_get_inbox(uid, db):
        return SimpleNamespace(id=inbox_id)
    monkeypatch.setattr(classifier_service.inbox_service, "get_or_create_inbox", fake_get_inbox)

    result = await classifier_service.classify_into_project("any", user_id, None)
    assert result.fallback_to_inbox is True
    assert result.project_id == inbox_id


# ---------- HTTP contract tests --------------------------------------------

async def test_google_status_without_jwt_returns_disconnected():
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        resp = await client.get("/api/v1/google/status", headers=API_HEADERS)
        assert resp.status_code == 200
        assert resp.json() == {"connected": False}


async def test_skills_status_requires_jwt():
    """API-key without JWT must get 401 — skills are per-user."""
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        resp = await client.get(
            "/api/v1/skills/google-calendar/status", headers=API_HEADERS,
        )
        assert resp.status_code == 401


async def test_skills_sync_requires_jwt():
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        resp = await client.post(
            "/api/v1/skills/google-calendar/sync", headers=API_HEADERS,
        )
        assert resp.status_code == 401
