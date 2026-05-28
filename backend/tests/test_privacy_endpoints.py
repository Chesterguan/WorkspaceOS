"""PATCH endpoints for memory tag editing + project privacy default."""
from __future__ import annotations

import uuid

import pytest

from app.models.memory import MemoryEntry
from app.models.project import Project
from app.database import AsyncSessionLocal
from app.services.privacy_tags import LOCAL_ONLY, REDACT_CONTENT, PUBLIC


# ── Memory tags ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_memory_tags_replaces_tag_list(client, jwt_headers, sample_project):
    """PATCH /memory/{id}/tags replaces the tag list and persists privacy:* values."""
    async with AsyncSessionLocal() as db:
        entry = MemoryEntry(
            project_id=sample_project.id,
            entry_type="narrative_fact",
            content="something",
            metadata_={"tags": ["topic:old"]},
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        entry_id = entry.id

    r = await client.patch(
        f"/api/v1/memory/{entry_id}/tags",
        headers=jwt_headers,
        json={"tags": [LOCAL_ONLY, "topic:new"]},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert LOCAL_ONLY in body["tags"]
    assert "topic:old" not in body["tags"]

    # Verify persisted
    async with AsyncSessionLocal() as db:
        reloaded = await db.get(MemoryEntry, entry_id)
        assert LOCAL_ONLY in (reloaded.metadata_ or {}).get("tags", [])


@pytest.mark.asyncio
async def test_patch_memory_tags_collapses_multiple_privacy_tags(client, jwt_headers, sample_project):
    """Multiple privacy:* tags in one request — last writer wins, others dropped."""
    async with AsyncSessionLocal() as db:
        entry = MemoryEntry(
            project_id=sample_project.id,
            entry_type="narrative_fact",
            content="x",
            metadata_={"tags": []},
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        entry_id = entry.id

    r = await client.patch(
        f"/api/v1/memory/{entry_id}/tags",
        headers=jwt_headers,
        json={"tags": [LOCAL_ONLY, REDACT_CONTENT, PUBLIC, "topic:foo"]},
    )

    assert r.status_code == 200, r.text
    final_tags = r.json()["tags"]
    privacy_tags = [t for t in final_tags if t.startswith("privacy:")]
    assert len(privacy_tags) == 1, f"expected exactly one privacy tag, got {privacy_tags}"
    assert privacy_tags[0] == PUBLIC, "expected last-listed privacy tag to win"
    assert "topic:foo" in final_tags


@pytest.mark.asyncio
async def test_patch_memory_tags_404_when_not_found(client, jwt_headers):
    r = await client.patch(
        f"/api/v1/memory/{uuid.uuid4()}/tags",
        headers=jwt_headers,
        json={"tags": []},
    )
    assert r.status_code == 404


# ── Project privacy default ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_project_privacy_default_strict(client, jwt_headers, sample_project):
    r = await client.patch(
        f"/api/v1/projects/{sample_project.id}/privacy-default",
        headers=jwt_headers,
        json={"privacy_default": "strict"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["privacy_default"] == "strict"

    # Verify persisted
    async with AsyncSessionLocal() as db:
        reloaded = await db.get(Project, sample_project.id)
        assert reloaded.privacy_default == "strict"


@pytest.mark.asyncio
async def test_patch_project_privacy_default_rejects_invalid_value(client, jwt_headers, sample_project):
    r = await client.patch(
        f"/api/v1/projects/{sample_project.id}/privacy-default",
        headers=jwt_headers,
        json={"privacy_default": "banana"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_patch_project_privacy_default_404_when_not_yours(client, jwt_headers):
    """Project owned by another user must return 404 (don't reveal existence)."""
    other_user_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        from app.models.user import User
        other = User(
            id=other_user_id,
            email=f"other-{other_user_id.hex[:8]}@test.com",
        )
        db.add(other)
        await db.commit()

        proj = Project(
            user_id=other_user_id,
            name="other user's project",
            slug=f"other-{uuid.uuid4().hex[:8]}",
        )
        db.add(proj)
        await db.commit()
        await db.refresh(proj)
        other_proj_id = proj.id

    try:
        r = await client.patch(
            f"/api/v1/projects/{other_proj_id}/privacy-default",
            headers=jwt_headers,
            json={"privacy_default": "strict"},
        )
        assert r.status_code == 404
    finally:
        # Clean up — cascades to the project via FK
        async with AsyncSessionLocal() as db:
            from sqlalchemy import delete
            from app.models.user import User as _User
            await db.execute(delete(_User).where(_User.id == other_user_id))
            await db.commit()
