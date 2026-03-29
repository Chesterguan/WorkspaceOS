import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class ChatSendRequest(BaseModel):
    message: str
    # Context toggles — all default to True so the AI has full context by default
    include_workspace: bool = True
    include_memory: bool = True
    include_repo: bool = True


class ChatMessageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    project_id: uuid.UUID
    role: str
    content: str
    # metadata_ is the Python attribute name; the column is "metadata"
    metadata_: Optional[dict]
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageResponse]
    total: int
