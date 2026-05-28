"""EgressRecorder records per-call field byte breakdown + redaction
summary, emits a TUI event, and persists a row to egress_logs."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

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
