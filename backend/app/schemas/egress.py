"""Pydantic schemas for the egress audit router."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class EgressRecord(BaseModel):
    id: uuid.UUID
    ts: datetime
    project_id: Optional[uuid.UUID]
    surface: str
    service: str
    provider: str
    model: Optional[str]
    fields: Dict[str, int]
    redaction: Optional[Dict]
    total_bytes: int


class EgressRecentResponse(BaseModel):
    records: List[EgressRecord]
    total_bytes_today: int
