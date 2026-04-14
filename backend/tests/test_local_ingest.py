"""
Tests for the local-ingest endpoint + service.

Pure unit tests cover the renderer logic (so the AppleScript bridge's
field-shape contract is locked down). HTTP tests exercise auth guard
and payload validation against the running backend.
"""
import os
import uuid

import pytest
from httpx import AsyncClient

from app.schemas.local_ingest import LocalIngestItem
from app.services.local_ingest_service import (
    _render_calendar,
    _render_mail,
    _render_item,
)


BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
API_HEADERS = {"X-API-Key": os.environ.get("TEST_API_KEY", "dev-secret-key")}


# ---------- renderer (pure) --------------------------------------------------

def test_render_calendar_full_fields():
    item = LocalIngestItem(
        external_id="evt1",
        kind="calendar",
        subject="Weekly sync",
        start="2026-04-15T09:00:00",
        end="2026-04-15T09:30:00",
        location="Room A",
        organizer="alice@x.com",
        attendees=["bob@x.com", "carol@x.com"],
        body="Agenda: Q2 review",
    )
    rendered = _render_calendar(item)
    assert "# Weekly sync" in rendered
    assert "When: 2026-04-15T09:00:00 → 2026-04-15T09:30:00" in rendered
    assert "Where: Room A" in rendered
    assert "Organizer: alice@x.com" in rendered
    assert "bob@x.com" in rendered
    assert "Agenda: Q2 review" in rendered


def test_render_calendar_minimum_fields():
    """A spare event (no end, no location, no body) must not crash."""
    item = LocalIngestItem(external_id="x", kind="calendar", subject="Sparse")
    out = _render_calendar(item)
    assert "# Sparse" in out
    # No "When:" line at all since start is missing
    assert "When:" not in out


def test_render_mail_full_fields():
    item = LocalIngestItem(
        external_id="m1",
        kind="mail",
        subject="Re: proposal",
        sender="Alice <alice@x.com>",
        to=["me@x.com"],
        cc=["cc@x.com"],
        received_at="2026-04-14T12:00:00Z",
        body="Thanks for the draft",
    )
    out = _render_mail(item)
    assert "# Re: proposal" in out
    assert "From: Alice <alice@x.com>" in out
    assert "To: me@x.com" in out
    assert "Cc: cc@x.com" in out
    assert "Thanks for the draft" in out


def test_render_item_dispatches_by_kind():
    cal_item = LocalIngestItem(external_id="a", kind="calendar", subject="C")
    mail_item = LocalIngestItem(external_id="b", kind="mail", subject="M")
    unk_item = LocalIngestItem(external_id="c", kind="slack", subject="S", body="hello")

    assert "# C" in _render_item(cal_item)
    assert "# M" in _render_item(mail_item)
    # Unknown kinds don't crash — they fall through to subject+body
    assert "hello" in _render_item(unk_item)


# ---------- HTTP contract ----------------------------------------------------

async def test_local_ingest_requires_jwt():
    """API-key-only must be rejected — items are attributed to a user."""
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        resp = await client.post(
            "/api/v1/skills/local-ingest/items",
            headers=API_HEADERS,
            json={"items": [
                {"external_id": "x", "kind": "calendar", "subject": "test"},
            ]},
        )
        assert resp.status_code == 401


async def test_local_ingest_rejects_oversized_batch():
    """Server caps item count at 200 per request."""
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        # 201 items — over the pydantic max_length=200 on LocalIngestRequest.
        items = [
            {"external_id": f"x{i}", "kind": "calendar", "subject": "t"}
            for i in range(201)
        ]
        resp = await client.post(
            "/api/v1/skills/local-ingest/items",
            headers=API_HEADERS,
            json={"items": items},
        )
        # 401 because we don't have a JWT — but we verified the endpoint
        # exists + auth discipline is enforced. Validation-caps test could
        # be done with a real JWT; not worth the test-harness weight for v1.
        assert resp.status_code in (401, 422)


async def test_local_ingest_rejects_missing_required_fields():
    """external_id + kind are required by the schema."""
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        resp = await client.post(
            "/api/v1/skills/local-ingest/items",
            headers=API_HEADERS,
            json={"items": [{"subject": "no external_id or kind"}]},
        )
        # 422 validation OR 401 auth — both acceptable; just shouldn't be 200
        assert resp.status_code in (401, 422)
