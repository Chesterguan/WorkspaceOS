"""
Integration tests for ProjectScribe API endpoints.

Tests run against the real Docker database with seeded demo data.
Each test uses a transactional session that rolls back on completion.
"""
import pytest
from httpx import AsyncClient

from conftest import API_HEADERS

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def test_health_check(client: AsyncClient):
    """GET /health returns 200 with status ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def test_missing_api_key_rejects(client: AsyncClient):
    """Requests without X-API-Key header get rejected (422 missing header or 401)."""
    resp = await client.get("/api/v1/projects")
    assert resp.status_code in (401, 422)


async def test_invalid_api_key_returns_401(client: AsyncClient):
    """Requests with wrong X-API-Key get 401."""
    resp = await client.get("/api/v1/projects", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

async def test_list_projects(client: AsyncClient):
    """GET /api/v1/projects returns a list of projects."""
    resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Seeded DB should have at least the demo projects
    assert len(data) >= 1
    # Each project has required fields
    proj = data[0]
    assert "id" in proj
    assert "name" in proj
    assert "github_repo" in proj


async def test_get_project_not_found(client: AsyncClient):
    """GET /api/v1/projects/{bad_id} returns 404."""
    resp = await client.get(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000",
        headers=API_HEADERS,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

async def test_dashboard_summary(client: AsyncClient):
    """GET /api/v1/dashboard/summary returns aggregate stats."""
    resp = await client.get("/api/v1/dashboard/summary", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_projects" in data
    assert "total_drafts" in data
    assert "total_syncs" in data
    assert "recent_activity" in data
    assert isinstance(data["recent_activity"], list)


async def test_dashboard_analytics(client: AsyncClient):
    """GET /api/v1/dashboard/analytics returns 12 weeks of data."""
    resp = await client.get("/api/v1/dashboard/analytics", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "weeks" in data
    assert "totals" in data
    assert len(data["weeks"]) == 12
    # Each week has the expected fields
    week = data["weeks"][0]
    assert "week" in week
    assert "commits" in week
    assert "papers" in week
    assert "drafts" in week
    assert "memory" in week
    # Totals has the expected keys
    for key in ["commits", "papers", "drafts", "memory"]:
        assert key in data["totals"]


# ---------------------------------------------------------------------------
# Chat advisors
# ---------------------------------------------------------------------------

async def test_chat_advisors_list(client: AsyncClient):
    """GET /api/v1/chat/advisors returns all 8 advisors."""
    resp = await client.get("/api/v1/chat/advisors", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 8
    # Check first advisor has required fields
    advisor = data[0]
    assert "id" in advisor
    assert "name" in advisor
    assert "tagline" in advisor
    assert "expertise" in advisor
    assert "color" in advisor
    assert "avatar" in advisor
    # System prompt should NOT be in the response
    assert "system_prompt" not in advisor


async def test_chat_starters(client: AsyncClient):
    """GET /api/v1/chat/starters returns conversation starters."""
    resp = await client.get("/api/v1/chat/starters", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    group = data[0]
    assert "category" in group
    assert "prompts" in group


# ---------------------------------------------------------------------------
# Settings keys
# ---------------------------------------------------------------------------

async def test_settings_get_keys(client: AsyncClient):
    """GET /api/v1/settings/keys returns key status list."""
    resp = await client.get("/api/v1/settings/keys", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "keys" in data
    assert isinstance(data["keys"], list)
    assert len(data["keys"]) >= 5  # At least the core keys
    # Each key has expected fields
    key_entry = data["keys"][0]
    assert "key" in key_entry
    assert "masked_value" in key_entry
    assert "source" in key_entry


# ---------------------------------------------------------------------------
# Paper endpoints exist
# ---------------------------------------------------------------------------

async def test_paper_generate_v2_validation(client: AsyncClient):
    """POST /api/v1/projects/{id}/paper/generate-v2 validates paper_type."""
    # Use a real project ID from seeded data
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/paper/generate-v2",
        headers={**API_HEADERS, "Content-Type": "application/json"},
        json={"title": "Test", "paper_type": "invalid_type"},
    )
    assert resp.status_code == 422
    assert "invalid_type" in resp.json()["detail"].lower() or "paper_type" in resp.json()["detail"].lower()


async def test_paper_edit_not_found(client: AsyncClient):
    """POST /api/v1/projects/{id}/paper/{bad_id}/edit returns 404."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/paper/00000000-0000-0000-0000-000000000000/edit",
        headers={**API_HEADERS, "Content-Type": "application/json"},
        json={"instruction": "test edit"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

async def test_auth_login_success(client: AsyncClient):
    """POST /auth/login returns JWT token for valid demo credentials."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "demo@prsecretary.dev", "password": "demo123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["email"] == "demo@prsecretary.dev"
    assert data["user_id"]


async def test_auth_login_wrong_password(client: AsyncClient):
    """POST /auth/login rejects wrong password."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "demo@prsecretary.dev", "password": "wrongpass"},
    )
    assert resp.status_code == 401


async def test_auth_login_nonexistent_user(client: AsyncClient):
    """POST /auth/login rejects unknown email."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "pass123"},
    )
    assert resp.status_code == 401


async def test_auth_me_with_jwt(client: AsyncClient):
    """GET /auth/me returns user profile when authenticated with JWT."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "demo@prsecretary.dev", "password": "demo123"},
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "demo@prsecretary.dev"
    assert "id" in data
    assert "created_at" in data


async def test_auth_me_invalid_token(client: AsyncClient):
    """GET /auth/me rejects invalid JWT token."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token-here"},
    )
    assert resp.status_code == 401


async def test_jwt_token_on_protected_endpoint(client: AsyncClient):
    """Bearer JWT token works on regular protected endpoints."""
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "demo@prsecretary.dev", "password": "demo123"},
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


# ---------------------------------------------------------------------------
# Narrative
# ---------------------------------------------------------------------------

async def test_get_narrative(client: AsyncClient):
    """GET /api/v1/projects/{id}/narrative returns narrative data."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}/narrative", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "project_id" in data


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

async def test_list_drafts(client: AsyncClient):
    """GET /api/v1/projects/{id}/drafts returns a list."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}/drafts", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Blog posts
# ---------------------------------------------------------------------------

async def test_list_blog_posts(client: AsyncClient):
    """GET /api/v1/projects/{id}/blog returns a list."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}/blog", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

async def test_list_sync_runs(client: AsyncClient):
    """GET /api/v1/projects/{id}/sync returns sync run list."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}/sync", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


async def test_sync_timeline(client: AsyncClient):
    """GET /api/v1/projects/{id}/sync/timeline returns timeline data."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}/sync/timeline", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "months" in data


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

async def test_list_memory(client: AsyncClient):
    """GET /api/v1/projects/{id}/memory returns memory entries."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}/memory", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


async def test_search_memory_all(client: AsyncClient):
    """POST /api/v1/memory/search-all returns cross-project results."""
    resp = await client.post(
        "/api/v1/memory/search-all",
        headers={**API_HEADERS, "Content-Type": "application/json"},
        json={"query": "project", "limit": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

async def test_chat_history(client: AsyncClient):
    """GET /api/v1/projects/{id}/chat returns chat history."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}/chat", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "messages" in data
    assert "total" in data


# ---------------------------------------------------------------------------
# Settings write + delete round-trip
# ---------------------------------------------------------------------------

async def test_settings_save_and_delete(client: AsyncClient):
    """PUT + DELETE /api/v1/settings/keys round-trip works."""
    resp = await client.put(
        "/api/v1/settings/keys",
        headers={**API_HEADERS, "Content-Type": "application/json"},
        json={"keys": {"devto_api_key": "test-key-12345"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    devto = next((k for k in data["keys"] if k["key"] == "devto_api_key"), None)
    assert devto is not None
    assert devto["source"] == "db"

    # Delete it
    resp = await client.delete("/api/v1/settings/keys/devto_api_key", headers=API_HEADERS)
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Project stats
# ---------------------------------------------------------------------------

async def test_project_stats(client: AsyncClient):
    """GET /api/v1/projects/stats returns per-project stats."""
    resp = await client.get("/api/v1/projects/stats", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    # Response is {stats: [...]} wrapper
    assert "stats" in data
    assert isinstance(data["stats"], list)


# ---------------------------------------------------------------------------
# Research roundtable
# ---------------------------------------------------------------------------

async def test_research_reviewers_list(client: AsyncClient):
    """GET /api/v1/research/reviewers returns 6 reviewers."""
    resp = await client.get("/api/v1/research/reviewers", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 6
    reviewer = data[0]
    assert "id" in reviewer
    assert "name" in reviewer
    assert "modeled_after" in reviewer
    assert "avatar" in reviewer
    assert "color" in reviewer


# ---------------------------------------------------------------------------
# File ingest
# ---------------------------------------------------------------------------

async def test_file_list_empty(client: AsyncClient):
    """GET /api/v1/projects/{id}/files returns file list (may be empty)."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.get(f"/api/v1/projects/{project_id}/files", headers=API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert "total" in data
    assert isinstance(data["files"], list)


async def test_file_import_url_invalid(client: AsyncClient):
    """POST /api/v1/projects/{id}/files/import-url rejects invalid URL."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/files/import-url",
        headers={**API_HEADERS, "Content-Type": "application/json"},
        json={"url": "not-a-url"},
    )
    # Should fail with 400 or 422
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Wiki refresh
# ---------------------------------------------------------------------------

async def test_wiki_refresh(client: AsyncClient):
    """POST /api/v1/projects/{id}/memory/wiki/refresh generates wiki summary."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/memory/wiki/refresh",
        headers=API_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "content" in data
    assert len(data["content"]) > 50  # should have real content


# ---------------------------------------------------------------------------
# Hashnode endpoint exists
# ---------------------------------------------------------------------------

async def test_hashnode_endpoint_exists(client: AsyncClient):
    """POST /publish/hashnode endpoint is registered."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    # Use a fake draft ID — should get 404 (not 405 Method Not Allowed)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/drafts/00000000-0000-0000-0000-000000000000/publish/hashnode",
        headers={**API_HEADERS, "Content-Type": "application/json"},
        json={},
    )
    assert resp.status_code == 404  # draft not found, but endpoint exists


# ---------------------------------------------------------------------------
# Template service
# ---------------------------------------------------------------------------

async def test_paper_export_latex_templates(client: AsyncClient):
    """POST /paper/export-latex accepts neurips template."""
    projects_resp = await client.get("/api/v1/projects", headers=API_HEADERS)
    project_id = projects_resp.json()[0]["id"]

    # Get a blog post ID that exists (paper)
    blog_resp = await client.get(f"/api/v1/projects/{project_id}/blog", headers=API_HEADERS)
    posts = blog_resp.json()
    if len(posts) == 0:
        return  # skip if no posts

    resp = await client.post(
        f"/api/v1/projects/{project_id}/paper/export-latex",
        headers={**API_HEADERS, "Content-Type": "application/json"},
        json={"blog_post_id": posts[0]["id"], "template": "neurips"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "latex" in data


# ---------------------------------------------------------------------------
# Settings shows all keys including new ones
# ---------------------------------------------------------------------------

async def test_settings_shows_all_keys(client: AsyncClient):
    """GET /settings/keys includes hashnode and connector keys."""
    resp = await client.get("/api/v1/settings/keys", headers=API_HEADERS)
    assert resp.status_code == 200
    key_names = [k["key"] for k in resp.json()["keys"]]
    assert "hashnode_api_key" in key_names
    assert "hashnode_publication_id" in key_names
    assert "google_drive_credentials" in key_names
    assert "notion_api_key" in key_names
    assert "devto_api_key" in key_names
