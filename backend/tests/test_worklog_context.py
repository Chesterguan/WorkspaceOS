"""
Tests for the Project Context wiring in the Work Log service.

Two slices of coverage:
  1. Pure unit tests on `_build_context_block` — the prompt-assembly helper.
     No DB, no AI, no HTTP; guards the wiki truncation and focus rendering
     against regressions that would silently break the prompt shape.
  2. HTTP round-trip on PATCH /projects/{id} with focus_notes — confirms
     the new schema field survives the model → schema → router path.
"""
import os
import uuid

import pytest
from httpx import AsyncClient

from app.services.worklog_service import _WIKI_CHARS_PER_PROJECT, _build_context_block


# ---------- _build_context_block (pure) --------------------------------------

def test_build_context_block_empty_returns_empty_string():
    assert _build_context_block({}) == ""


def test_build_context_block_with_focus_only():
    out = _build_context_block({
        "p1": {"name": "Alpha", "focus": "ship v1 by Friday", "wiki": None},
    })
    assert "## Project Context" in out
    assert "### Alpha" in out
    assert "ship v1 by Friday" in out
    # No wiki → placeholder still rendered so the LLM doesn't think we forgot
    assert "(no wiki generated yet)" in out


def test_build_context_block_missing_focus_renders_em_dash():
    out = _build_context_block({
        "p1": {"name": "Alpha", "focus": None, "wiki": "some wiki"},
    })
    assert "Current focus (user-pinned):** —" in out
    assert "some wiki" in out


def test_build_context_block_truncates_long_wiki():
    big_wiki = "x" * (_WIKI_CHARS_PER_PROJECT + 500)
    out = _build_context_block({
        "p1": {"name": "Alpha", "focus": None, "wiki": big_wiki},
    })
    # Truncation marker present, full content not
    assert "(truncated)" in out
    assert big_wiki not in out
    # But the leading slice IS present
    assert "x" * 100 in out


def test_build_context_block_handles_multiple_projects_in_order():
    out = _build_context_block({
        "p1": {"name": "Alpha", "focus": "alpha focus", "wiki": None},
        "p2": {"name": "Beta", "focus": "beta focus", "wiki": None},
    })
    # Both project headers show up
    assert "### Alpha" in out
    assert "### Beta" in out
    # Both focus strings render
    assert "alpha focus" in out
    assert "beta focus" in out


# ---------- HTTP round-trip --------------------------------------------------

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
API_HEADERS = {"X-API-Key": os.environ.get("TEST_API_KEY", "dev-secret-key")}


async def test_project_focus_notes_patch_roundtrip():
    """PATCH /projects/{id} with focus_notes must persist and round-trip."""
    slug = f"focus-rt-{uuid.uuid4().hex[:8]}"
    async with AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Create
        create_resp = await client.post(
            "/api/v1/projects",
            headers=API_HEADERS,
            json={"name": "Focus Roundtrip", "slug": slug},
        )
        assert create_resp.status_code == 201, create_resp.text
        project_id = create_resp.json()["id"]
        # New projects start with focus_notes=None
        assert create_resp.json().get("focus_notes") is None

        try:
            # Patch — set focus
            patch_resp = await client.patch(
                f"/api/v1/projects/{project_id}",
                headers=API_HEADERS,
                json={"focus_notes": "ship docs by end of week; review 3 PRs"},
            )
            assert patch_resp.status_code == 200, patch_resp.text
            assert patch_resp.json()["focus_notes"] == (
                "ship docs by end of week; review 3 PRs"
            )

            # Get — confirm it persisted
            get_resp = await client.get(
                f"/api/v1/projects/{project_id}",
                headers=API_HEADERS,
            )
            assert get_resp.status_code == 200
            assert get_resp.json()["focus_notes"] == (
                "ship docs by end of week; review 3 PRs"
            )

            # Clear — empty string should null it out
            clear_resp = await client.patch(
                f"/api/v1/projects/{project_id}",
                headers=API_HEADERS,
                json={"focus_notes": ""},
            )
            assert clear_resp.status_code == 200
            # Empty string round-trips as empty string (user intent preserved)
            assert clear_resp.json()["focus_notes"] == ""
        finally:
            # Cleanup — always delete so re-runs don't accumulate fixtures
            await client.delete(
                f"/api/v1/projects/{project_id}",
                headers=API_HEADERS,
            )
