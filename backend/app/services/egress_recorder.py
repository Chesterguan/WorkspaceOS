"""EgressRecorder — context manager that records per-call cloud-egress.

Usage:
    async with EgressRecorder(
        surface="paper", service="paper_service.generate_paper",
        provider="gemini", model=settings.gemini_chat_model,
        user_id=user_id, project_id=project_id,
    ) as rec:
        rec.field("paper_body", body_text)
        rec.field("venue", venue_text)
        rec.redaction_summary(redaction)
        result = await ai.complete(system, user)

The recorder emits a `data.egress` event to the bench TUI on exit
and persists one row to egress_logs.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.database import AsyncSessionLocal
from app.models.egress_log import EgressLog
from app.services.event_stream import emit

logger = logging.getLogger(__name__)


@dataclass
class RedactionSummary:
    spans_replaced: int = 0
    bytes_replaced: int = 0
    categories: Dict[str, int] = field(default_factory=dict)
    entries_stubbed: int = 0


class EgressRecorder:
    def __init__(
        self,
        surface: str,
        service: str,
        provider: str,
        model: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
    ) -> None:
        self.surface = surface
        self.service = service
        self.provider = provider
        self.model = model
        self.user_id = user_id
        self.project_id = project_id
        self._fields: Dict[str, int] = {}
        self._redaction: Optional[RedactionSummary] = None
        self._tokens_estimated: Optional[int] = None

    def field(self, name: str, payload: str) -> None:
        """Record one named field of the egress payload."""
        self._fields[name] = self._fields.get(name, 0) + len(payload.encode("utf-8"))

    def redaction_summary(self, summary: RedactionSummary) -> None:
        self._redaction = summary

    def tokens(self, n: int) -> None:
        self._tokens_estimated = n

    async def __aenter__(self) -> "EgressRecorder":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # We persist even on exception so failed cloud calls still appear
        # in the audit log (the user can see what we attempted to send).
        total_bytes = sum(self._fields.values())
        payload = {
            "ts": datetime.now(tz=timezone.utc),
            "surface": self.surface,
            "service": self.service,
            "provider": self.provider,
            "model": self.model,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "fields": dict(self._fields),
            "redaction": self._redaction.__dict__ if self._redaction else None,
            "tokens_estimated": self._tokens_estimated,
            "total_bytes": total_bytes,
        }
        try:
            await _persist(payload)
        except Exception:
            logger.exception("egress_recorder: persist failed (non-fatal)")
        try:
            redaction_blurb = ""
            if self._redaction:
                redaction_blurb = (
                    f" — {self._redaction.entries_stubbed} stubbed, "
                    f"{self._redaction.spans_replaced} spans replaced "
                    f"({self._redaction.bytes_replaced} B)"
                )
            emit(
                "info",
                "data.egress",
                f"{self.service} → {self.provider}: {total_bytes} B sent{redaction_blurb}",
                project_id=str(self.project_id) if self.project_id else None,
                meta={
                    "surface": self.surface,
                    "service": self.service,
                    "provider": self.provider,
                    "model": self.model,
                    "fields": dict(self._fields),
                    "redaction": self._redaction.__dict__ if self._redaction else None,
                    "total_bytes": total_bytes,
                },
            )
        except Exception:
            logger.exception("egress_recorder: emit failed (non-fatal)")


async def _persist(payload: Dict[str, Any]) -> None:
    """Write one egress_logs row. Separated so tests can monkeypatch."""
    async with AsyncSessionLocal() as db:
        user_id = payload["user_id"]
        project_id = payload["project_id"]
        # Backfill the owner from the project when the call site only had a
        # project in scope. The audit feed (GET /egress/recent) filters
        # strictly on user_id, so a NULL here makes the row invisible to the
        # very user it belongs to. Project ownership is the user, so this is
        # the correct attribution. One extra read per cloud call, off the
        # request path.
        if user_id is None and project_id is not None:
            from sqlalchemy import select

            from app.models.project import Project

            user_id = (
                await db.execute(
                    select(Project.user_id).where(Project.id == project_id)
                )
            ).scalar_one_or_none()

        row = EgressLog(
            ts=payload["ts"],
            user_id=user_id,
            project_id=project_id,
            surface=payload["surface"],
            service=payload["service"],
            provider=payload["provider"],
            model=payload["model"],
            fields=payload["fields"],
            redaction=payload["redaction"],
            tokens_estimated=payload["tokens_estimated"],
            total_bytes=payload["total_bytes"],
        )
        db.add(row)
        await db.commit()
