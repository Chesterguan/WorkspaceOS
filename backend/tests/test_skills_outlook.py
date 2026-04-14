"""
Outlook skill HTTP contract tests.

The actual ingest functions can't be integration-tested without a real
Microsoft account, so here we cover: the endpoints exist, refuse API-key-only
calls, and return a sane default when the user hasn't connected.

Ingest logic (Graph payload → text blob) is unit-tested against fixture
dicts so we don't need a live Graph client to validate the formatting.
"""
import os
import uuid

import pytest
from httpx import AsyncClient

from app.services.outlook_calendar_service import _format_event_text, _strip_html
from app.services.outlook_mail_service import _addrs, _format_mail_text


BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8000")
API_HEADERS = {"X-API-Key": os.environ.get("TEST_API_KEY", "dev-secret-key")}


# ---------- Graph payload formatters (pure) ---------------------------------

def test_strip_html_handles_entities():
    assert _strip_html("<p>hi &amp; bye</p>") == "hi & bye"
    assert _strip_html("") == ""
    assert _strip_html(None) == ""  # type: ignore[arg-type]


def test_format_event_text_with_full_payload():
    event = {
        "id": "abc",
        "subject": "Weekly sync",
        "start": {"dateTime": "2026-04-15T09:00:00"},
        "end": {"dateTime": "2026-04-15T09:30:00"},
        "location": {"displayName": "Room A"},
        "organizer": {"emailAddress": {"name": "Alice", "address": "alice@x.com"}},
        "attendees": [
            {"emailAddress": {"address": "bob@x.com"}},
            {"emailAddress": {"address": "carol@x.com"}},
        ],
        "body": {"content": "<p>Agenda: <strong>Q2</strong> review</p>"},
    }
    out = _format_event_text(event)
    assert "# Weekly sync" in out
    assert "When: 2026-04-15T09:00:00 → 2026-04-15T09:30:00" in out
    assert "Where: Room A" in out
    assert "Organizer: alice@x.com" in out
    assert "bob@x.com" in out
    assert "Agenda: Q2 review" in out  # HTML stripped


def test_format_event_text_minimum_payload():
    """Missing optional fields must not crash the formatter."""
    out = _format_event_text({"id": "x", "subject": "bare"})
    assert "# bare" in out
    assert "When: unknown" in out


def test_mail_addrs_filters_and_renders():
    recips = [
        {"emailAddress": {"name": "Alice", "address": "alice@x.com"}},
        {"emailAddress": {"address": "bob@x.com"}},
        {"emailAddress": {}},  # dropped — no address
    ]
    assert _addrs(recips) == ["Alice <alice@x.com>", "bob@x.com"]


def test_format_mail_text_with_full_payload():
    msg = {
        "id": "m1",
        "subject": "Re: proposal",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@x.com"}},
        "toRecipients": [{"emailAddress": {"address": "me@x.com"}}],
        "ccRecipients": [{"emailAddress": {"address": "cc@x.com"}}],
        "receivedDateTime": "2026-04-14T12:00:00Z",
        "bodyPreview": "Thanks for the draft — a few small tweaks…",
    }
    out = _format_mail_text(msg)
    assert "# Re: proposal" in out
    assert "From: Alice <alice@x.com>" in out
    assert "To: me@x.com" in out
    assert "Cc: cc@x.com" in out
    assert "Received: 2026-04-14T12:00:00Z" in out
    assert "Thanks for the draft" in out


# ---------- HTTP contract ---------------------------------------------------

async def test_microsoft_status_without_jwt():
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        resp = await client.get("/api/v1/microsoft/status", headers=API_HEADERS)
        assert resp.status_code == 200
        assert resp.json() == {"connected": False}


async def test_outlook_calendar_skill_requires_jwt():
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        s = await client.get(
            "/api/v1/skills/outlook-calendar/status", headers=API_HEADERS,
        )
        assert s.status_code == 401
        p = await client.post(
            "/api/v1/skills/outlook-calendar/sync", headers=API_HEADERS,
        )
        assert p.status_code == 401


async def test_outlook_mail_skill_requires_jwt():
    async with AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        s = await client.get(
            "/api/v1/skills/outlook-mail/status", headers=API_HEADERS,
        )
        assert s.status_code == 401
        p = await client.post(
            "/api/v1/skills/outlook-mail/sync", headers=API_HEADERS,
        )
        assert p.status_code == 401
