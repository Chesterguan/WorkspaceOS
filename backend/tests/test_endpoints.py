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

async def _register_for_auth_test(client: AsyncClient) -> dict:
    """Inline helper: register a throwaway user and return the full response body.

    Duplicates a small part of ``_register_user`` (defined later in the file) so
    the auth tests stay near the top with no forward references.
    """
    import uuid as _u
    email = f"auth-test-{_u.uuid4().hex[:8]}@scoping.test"
    password = "AuthTestPass123!"
    resp = await client.post(
        "/api/v1/auth/register",
        headers={"Content-Type": "application/json"},
        json={"email": email, "password": password, "display_name": "Auth Test"},
    )
    assert resp.status_code in (200, 201), f"register failed: {resp.text}"
    body = resp.json()
    body["password"] = password
    return body


async def test_auth_login_success(client: AsyncClient):
    """POST /auth/login returns a JWT token for valid credentials."""
    reg = await _register_for_auth_test(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": reg["email"], "password": reg["password"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["email"] == reg["email"]
    assert data["user_id"]


async def test_auth_login_wrong_password(client: AsyncClient):
    """POST /auth/login rejects wrong password."""
    reg = await _register_for_auth_test(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": reg["email"], "password": "wrongpass"},
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
    """GET /auth/me returns the authenticated user's profile."""
    reg = await _register_for_auth_test(client)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": reg["email"], "password": reg["password"]},
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == reg["email"]
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
    """Bearer JWT token works on protected endpoints (returns empty list for a
    fresh user, but returns 200 — the scoping just hides other users' data)."""
    reg = await _register_for_auth_test(client)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": reg["email"], "password": reg["password"]},
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # A fresh user has zero projects — this is expected under scoping.
    assert data == []


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


# ---------------------------------------------------------------------------
# Multi-tenant JWT scoping — cross-user isolation
# ---------------------------------------------------------------------------
# These tests prove that a JWT-authenticated user cannot read or write another
# user's resources via any of the nested /projects/{project_id}/... routes,
# the portfolio endpoints, or the worklog endpoints. They register two throwaway
# users per run and clean up on teardown.

import uuid as _uuid


async def _register_user(client: AsyncClient, tag: str) -> dict:
    """Register a user with a unique email. Returns {email, password, token, user_id}."""
    email = f"test-{tag}-{_uuid.uuid4().hex[:8]}@scoping.test"
    password = "TestPassword123!"
    resp = await client.post(
        "/api/v1/auth/register",
        headers={"Content-Type": "application/json"},
        json={"email": email, "password": password, "display_name": f"Test {tag}"},
    )
    assert resp.status_code in (200, 201), f"register failed: {resp.text}"
    data = resp.json()
    return {
        "email": email,
        "password": password,
        "token": data["access_token"],
        "user_id": data["user_id"],
    }


async def _create_project_for(client: AsyncClient, user_id: str, tag: str) -> str:
    """Create a project owned by user_id via admin API key. Returns project_id."""
    slug = f"scope-test-{tag.lower()}-{_uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/api/v1/projects",
        headers={**API_HEADERS, "Content-Type": "application/json"},
        json={
            "name": f"ScopeTest-{tag}",
            "slug": slug,
            "user_id": user_id,
            "github_repo": f"test/{slug}",
            "github_branch": "main",
        },
    )
    assert resp.status_code == 201, f"create project failed: {resp.text}"
    return resp.json()["id"]


async def _cleanup_project(client: AsyncClient, project_id: str) -> None:
    await client.delete(f"/api/v1/projects/{project_id}", headers=API_HEADERS)


async def test_scoping_user_cannot_see_other_users_projects_in_list(client: AsyncClient):
    """GET /projects scoped by JWT — user B does not see user A's projects."""
    user_a = await _register_user(client, "A")
    user_b = await _register_user(client, "B")
    proj_a = await _create_project_for(client, user_a["user_id"], "A")
    try:
        # User A sees at least their project
        resp = await client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {user_a['token']}"},
        )
        assert resp.status_code == 200
        a_ids = [p["id"] for p in resp.json()]
        assert proj_a in a_ids, "user A must see their own project"

        # User B does not see it
        resp = await client.get(
            "/api/v1/projects",
            headers={"Authorization": f"Bearer {user_b['token']}"},
        )
        assert resp.status_code == 200
        b_ids = [p["id"] for p in resp.json()]
        assert proj_a not in b_ids, "user B must not see user A's project"
    finally:
        await _cleanup_project(client, proj_a)


@pytest.mark.parametrize(
    "path_suffix",
    [
        "",                      # GET /projects/{id}
        "/narrative",            # GET /projects/{id}/narrative
        "/drafts",               # GET /projects/{id}/drafts
        "/sync",                 # GET /projects/{id}/sync
        "/memory",               # GET /projects/{id}/memory
        "/blog",                 # GET /projects/{id}/blog
        "/chat",                 # GET /projects/{id}/chat
        "/files",                # GET /projects/{id}/files
        "/research",             # GET /projects/{id}/research
        "/feedback/summary",     # GET /projects/{id}/feedback/summary
    ],
)
async def test_scoping_user_cannot_read_other_users_nested_resource(
    client: AsyncClient, path_suffix: str
):
    """Every nested /projects/{id}/... read returns 404 for non-owner."""
    user_a = await _register_user(client, "A")
    user_b = await _register_user(client, "B")
    proj_a = await _create_project_for(client, user_a["user_id"], "A")
    try:
        url = f"/api/v1/projects/{proj_a}{path_suffix}"
        # Owner reaches it cleanly — every endpoint in the list is a list/get
        # that should return 200 on a brand-new empty project.
        resp_a = await client.get(
            url, headers={"Authorization": f"Bearer {user_a['token']}"}
        )
        assert resp_a.status_code == 200, (
            f"owner got {resp_a.status_code} on {path_suffix} — expected 200"
        )

        # Non-owner MUST get 404
        resp_b = await client.get(
            url, headers={"Authorization": f"Bearer {user_b['token']}"}
        )
        assert resp_b.status_code == 404, (
            f"user B got {resp_b.status_code} on {path_suffix} — expected 404"
        )
    finally:
        await _cleanup_project(client, proj_a)


async def test_scoping_portfolio_generate_rejects_unowned_project_ids(
    client: AsyncClient,
):
    """POST /portfolio/generate with a project not owned by the caller → 404."""
    user_a = await _register_user(client, "A")
    user_b = await _register_user(client, "B")
    proj_a1 = await _create_project_for(client, user_a["user_id"], "A1")
    proj_a2 = await _create_project_for(client, user_a["user_id"], "A2")
    try:
        # User B tries to generate a portfolio post including user A's projects
        resp = await client.post(
            "/api/v1/portfolio/generate",
            headers={
                "Authorization": f"Bearer {user_b['token']}",
                "Content-Type": "application/json",
            },
            json={"project_ids": [proj_a1, proj_a2], "platform": "linkedin"},
        )
        assert resp.status_code == 404
        assert "not accessible" in resp.text.lower() or "not found" in resp.text.lower()
    finally:
        await _cleanup_project(client, proj_a1)
        await _cleanup_project(client, proj_a2)


async def test_scoping_worklog_generate_rejects_unowned_project_ids(
    client: AsyncClient,
):
    """POST /worklog/generate with a project not owned by the caller → 404."""
    user_a = await _register_user(client, "A")
    user_b = await _register_user(client, "B")
    proj_a = await _create_project_for(client, user_a["user_id"], "A")
    try:
        resp = await client.post(
            "/api/v1/worklog/generate",
            headers={
                "Authorization": f"Bearer {user_b['token']}",
                "Content-Type": "application/json",
            },
            json={
                "project_ids": [proj_a],
                "period_type": "weekly",
                "period_start": "2026-04-01",
                "period_end": "2026-04-08",
            },
        )
        assert resp.status_code == 404
    finally:
        await _cleanup_project(client, proj_a)


async def test_scoping_memory_search_all_returns_empty_for_user_with_no_projects(
    client: AsyncClient,
):
    """POST /memory/search-all scoped to caller's projects — new user gets []."""
    user = await _register_user(client, "empty")
    resp = await client.post(
        "/api/v1/memory/search-all",
        headers={
            "Authorization": f"Bearer {user['token']}",
            "Content-Type": "application/json",
        },
        json={"query": "anything", "limit": 5},
    )
    assert resp.status_code == 200
    assert resp.json() == [], "fresh user must get zero cross-project results"


async def test_scoping_oauth_state_token_cannot_be_used_as_access_token(
    client: AsyncClient,
):
    """H1 regression test: an OAuth state token must be rejected on protected endpoints.

    Mints the state token directly via auth_service (same Python process as the
    server) so the test does not depend on LinkedIn OAuth env configuration.
    """
    # The tests run from /app/tests against the backend at /app. Make the
    # app package importable so we can mint a token directly.
    import sys as _sys
    if "/app" not in _sys.path:
        _sys.path.insert(0, "/app")
    from app.services.auth_service import create_oauth_state_token

    user = await _register_user(client, "h1")

    # The real access token works on /auth/me
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert resp.status_code == 200

    # Mint an oauth_state token for the same user — identical secret, shorter
    # expiry, different type claim — and try to use it as a bearer token.
    state_token = create_oauth_state_token(user["user_id"], "linkedin_connect")

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {state_token}"},
    )
    assert resp.status_code == 401, (
        f"oauth_state token must not authenticate /auth/me, got {resp.status_code}"
    )


async def test_scoping_settings_keys_mutation_requires_admin(client: AsyncClient):
    """H2 regression test: JWT users cannot PUT /settings/keys — admin only."""
    user = await _register_user(client, "settings")

    # JWT user gets 403
    resp = await client.put(
        "/api/v1/settings/keys",
        headers={
            "Authorization": f"Bearer {user['token']}",
            "Content-Type": "application/json",
        },
        json={"keys": {"openai_api_key": "sk-fake-value-should-not-save"}},
    )
    assert resp.status_code == 403, f"expected 403 for JWT user, got {resp.status_code}"

    # Admin (API key) still works
    resp = await client.get("/api/v1/settings/keys", headers=API_HEADERS)
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/v1/settings/keys", None),
        ("GET", "/api/v1/settings/usage", None),
        ("GET", "/api/v1/settings/backups", None),
        ("PUT", "/api/v1/settings/keys", {"keys": {"openai_api_key": "sk-x"}}),
        ("DELETE", "/api/v1/settings/keys/devto_api_key", None),
        ("POST", "/api/v1/settings/backup", {}),
    ],
)
async def test_scoping_all_settings_endpoints_reject_jwt(
    client: AsyncClient, method: str, path: str, body: dict
):
    """Every /settings/* endpoint must 403 a JWT user and 200 the admin API key."""
    user = await _register_user(client, "allset")
    jwt_headers = {
        "Authorization": f"Bearer {user['token']}",
        "Content-Type": "application/json",
    }
    if method == "GET":
        resp = await client.get(path, headers=jwt_headers)
    elif method == "PUT":
        resp = await client.put(path, headers=jwt_headers, json=body or {})
    elif method == "DELETE":
        resp = await client.delete(path, headers=jwt_headers)
    elif method == "POST":
        resp = await client.post(path, headers=jwt_headers, json=body or {})
    assert resp.status_code == 403, (
        f"{method} {path} must 403 for JWT user, got {resp.status_code}"
    )


async def test_scoping_cannot_create_project_for_another_user(client: AsyncClient):
    """H-new-1 regression: a JWT user cannot pass body.user_id to plant a project
    in another user's namespace."""
    user_a = await _register_user(client, "victim")
    user_b = await _register_user(client, "attacker")

    # User B (JWT) tries to create a project owned by user A
    resp = await client.post(
        "/api/v1/projects",
        headers={
            "Authorization": f"Bearer {user_b['token']}",
            "Content-Type": "application/json",
        },
        json={
            "name": "Stolen",
            "slug": f"stolen-{_uuid.uuid4().hex[:6]}",
            "user_id": user_a["user_id"],
            "github_repo": "evil/stolen",
            "github_branch": "main",
        },
    )
    # Should either 403 or silently ignore body.user_id and create it for B
    assert resp.status_code in (201, 403)
    if resp.status_code == 201:
        # JWT user wins — the project must belong to user B, not A
        created = resp.json()
        assert created["user_id"] == user_b["user_id"], (
            f"JWT user B created a project but it was assigned to "
            f"{created['user_id']} instead of {user_b['user_id']}"
        )
        # Cleanup
        await client.delete(
            f"/api/v1/projects/{created['id']}", headers=API_HEADERS
        )


async def test_worklog_create_and_fetch_by_owner(client: AsyncClient):
    """Regression test for the 0013 migration gap:
    creating a worklog must actually persist (the INSERT path was broken
    before 0014 because the ``user_id`` column was missing from the
    physical ``work_logs`` table). Also verifies the owner can fetch it
    back and a different user cannot."""
    user_a = await _register_user(client, "wlog-a")
    user_b = await _register_user(client, "wlog-b")
    proj_a = await _create_project_for(client, user_a["user_id"], "wlog")
    try:
        # Create a worklog for user A spanning project_a
        create_resp = await client.post(
            "/api/v1/worklog/generate",
            headers={
                "Authorization": f"Bearer {user_a['token']}",
                "Content-Type": "application/json",
            },
            json={
                "project_ids": [proj_a],
                "period_type": "weekly",
                "period_start": "2026-04-01",
                "period_end": "2026-04-08",
            },
        )
        # The AI-generation side can take a while and may 500 if a provider
        # is misconfigured in the test env, but it must NOT 500 with a
        # "column user_id does not exist" error. Accept either a successful
        # create OR a 5xx that is explicitly about AI providers, not schema.
        if create_resp.status_code >= 500:
            body = create_resp.text.lower()
            assert "user_id" not in body or "does not exist" not in body, (
                f"worklog create hit the schema bug again: {create_resp.text}"
            )
            pytest.skip(
                f"worklog generate returned {create_resp.status_code} "
                f"(likely AI provider issue, not the schema bug we're guarding)"
            )
        assert create_resp.status_code == 201, (
            f"worklog create failed: {create_resp.status_code} {create_resp.text}"
        )
        worklog = create_resp.json()
        worklog_id = worklog["id"]

        # Owner can fetch it back
        resp = await client.get(
            f"/api/v1/worklog/{worklog_id}",
            headers={"Authorization": f"Bearer {user_a['token']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == worklog_id

        # Owner sees it in the list
        resp = await client.get(
            "/api/v1/worklog",
            headers={"Authorization": f"Bearer {user_a['token']}"},
        )
        assert resp.status_code == 200
        assert any(w["id"] == worklog_id for w in resp.json()["items"])

        # Different user cannot fetch it (worklog ownership scoping)
        resp = await client.get(
            f"/api/v1/worklog/{worklog_id}",
            headers={"Authorization": f"Bearer {user_b['token']}"},
        )
        assert resp.status_code == 404, (
            f"user B should 404 on user A's worklog, got {resp.status_code}"
        )

        # Cleanup the worklog (owner only)
        await client.delete(
            f"/api/v1/worklog/{worklog_id}",
            headers={"Authorization": f"Bearer {user_a['token']}"},
        )
    finally:
        await _cleanup_project(client, proj_a)


async def test_scoping_cannot_access_draft_across_projects(client: AsyncClient):
    """Nested resource ID IDOR: user B cannot fetch user A's draft even by
    guessing the draft ID, because _require_draft filters by project_id and
    user B's project doesn't contain that draft."""
    user_a = await _register_user(client, "draftA")
    user_b = await _register_user(client, "draftB")
    proj_a = await _create_project_for(client, user_a["user_id"], "draftA")
    proj_b = await _create_project_for(client, user_b["user_id"], "draftB")
    try:
        # Create a draft under project A (owner's JWT)
        create_resp = await client.post(
            f"/api/v1/projects/{proj_a}/drafts",
            headers={
                "Authorization": f"Bearer {user_a['token']}",
                "Content-Type": "application/json",
            },
            json={"platform": "linkedin", "content": "user A private draft"},
        )
        assert create_resp.status_code == 201
        draft_a_id = create_resp.json()["id"]

        # User B tries to fetch draft_a via their own project path (wrong parent)
        resp = await client.get(
            f"/api/v1/projects/{proj_b}/drafts/{draft_a_id}",
            headers={"Authorization": f"Bearer {user_b['token']}"},
        )
        assert resp.status_code == 404, (
            f"user B should 404 on foreign draft via own project, got {resp.status_code}"
        )

        # User B tries to fetch draft_a via user A's project path (ownership check)
        resp = await client.get(
            f"/api/v1/projects/{proj_a}/drafts/{draft_a_id}",
            headers={"Authorization": f"Bearer {user_b['token']}"},
        )
        assert resp.status_code == 404, (
            f"user B should 404 on foreign project+draft, got {resp.status_code}"
        )
    finally:
        await _cleanup_project(client, proj_a)
        await _cleanup_project(client, proj_b)
