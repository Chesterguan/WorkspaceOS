"""EgressRecorder records per-call field byte breakdown + redaction
summary, emits a TUI event, and persists a row to egress_logs."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.database import AsyncSessionLocal
from app.services.egress_recorder import EgressRecorder, RedactionSummary


@pytest.mark.asyncio
async def test_recorder_records_field_bytes_and_total(monkeypatch):
    written: list = []

    async def fake_persist(rec_payload):
        written.append(rec_payload)

    monkeypatch.setattr("app.services.egress_recorder._persist", fake_persist)

    async with EgressRecorder(
        surface="paper",
        service="paper_service.generate_paper",
        provider="gemini",
        model="gemini-2.0-flash",
        user_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    ) as rec:
        rec.field("paper_body", "hello world")  # 11 bytes
        rec.field("venue", "ICML 2026")          # 9 bytes
        rec.redaction_summary(RedactionSummary(
            spans_replaced=2, bytes_replaced=42, categories={"name": 2}
        ))

    assert len(written) == 1
    payload = written[0]
    assert payload["surface"] == "paper"
    assert payload["fields"]["paper_body"] == 11
    assert payload["fields"]["venue"] == 9
    assert payload["total_bytes"] == 20
    assert payload["redaction"]["spans_replaced"] == 2


@pytest.mark.asyncio
async def test_persist_backfills_user_id_from_project_owner(db_session, sample_project):
    """H-1: a recorder with only project_id in scope must still land a row
    attributed to the project owner — otherwise the audit feed (which filters
    on user_id) never shows it. Persist runs for real against the DB here."""
    from sqlalchemy import select, delete
    from app.models.egress_log import EgressLog

    async with EgressRecorder(
        surface="drafts",
        service="blog_service.generate_blog",
        provider="gemini",
        model="gemini-2.0-flash",
        user_id=None,                       # call site had no user, only a project
        project_id=sample_project.id,
    ) as rec:
        rec.field("seed", "draft seed")

    # Read back from a fresh session (persist commits independently).
    async with AsyncSessionLocal() as check:
        row = (
            await check.execute(
                select(EgressLog).where(EgressLog.project_id == sample_project.id)
            )
        ).scalar_one()
        assert row.user_id == sample_project.user_id
        # Cleanup so reruns don't accumulate (FK CASCADE would also catch it
        # at sample_user teardown, but be explicit).
        await check.execute(delete(EgressLog).where(EgressLog.id == row.id))
        await check.commit()
