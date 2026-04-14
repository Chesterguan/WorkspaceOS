"""Request/response schemas for the local-ingest skill endpoint."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LocalIngestItem(BaseModel):
    """One calendar event or email delivered from a host-side bridge
    (currently the macOS Outlook AppleScript script). Deliberately
    permissive — unknown fields are accepted and ignored so the bridge
    can evolve without lockstep schema updates."""

    # Stable identifier from the source system. Combined with `kind` to
    # form the MemoryEntry source_ref; dedupe depends on this being
    # stable across bridge runs (Outlook Mac's `id` of event/message
    # satisfies this).
    external_id: str = Field(..., min_length=1, max_length=500)

    # "calendar" | "mail". Free-form VARCHAR so other local sources can
    # be added later; the renderer picks a layout based on this.
    kind: str = Field(..., min_length=1, max_length=30)

    subject: Optional[str] = Field(None, max_length=1000)
    body: Optional[str] = Field(None, max_length=10_000)

    # Calendar-only fields
    start: Optional[str] = None   # ISO string or free-form from AppleScript
    end: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None
    organizer: Optional[str] = None

    # Mail-only fields
    sender: Optional[str] = None
    to: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    received_at: Optional[str] = None

    # Anything else the bridge wanted to tag along — e.g. folder, flags,
    # categories. Not rendered in v1, just preserved in details.
    extra: Optional[Dict[str, Any]] = None


class LocalIngestRequest(BaseModel):
    items: List[LocalIngestItem] = Field(..., max_length=200)


class LocalIngestResponse(BaseModel):
    fetched: int
    created: int
    skipped: int
    inbox: int
    by_project: Dict[str, int]
