import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class ChatSendRequest(BaseModel):
    message: str
    advisor_id: Optional[str] = None  # specific advisor, or None for roundtable
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
    metadata_: Optional[dict] = None
    created_at: datetime
    advisor_id: Optional[str] = None
    advisor_name: Optional[str] = None


class ChatRoundtableResponse(BaseModel):
    messages: List[ChatMessageResponse]
    routed_advisors: List[str]
    roundtable_group: str


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageResponse]
    total: int


class AdvisorInfo(BaseModel):
    id: str
    name: str
    tagline: str
    expertise: List[str]
    color: str
    avatar: str
