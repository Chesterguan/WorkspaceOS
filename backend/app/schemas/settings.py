"""
Schemas for the settings endpoints (API key management).
"""
from typing import Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class KeyStatus(BaseModel):
    key: str
    masked_value: str
    updated_at: Optional[datetime] = None
    source: str = "db"  # "db" or "env"


class KeysStatusResponse(BaseModel):
    keys: List[KeyStatus]


class SetKeyRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1)


class SetKeysRequest(BaseModel):
    keys: Dict[str, str]  # {"gemini_api_key": "AIza...", "openai_api_key": "sk-..."}


class DeleteKeyRequest(BaseModel):
    key: str
