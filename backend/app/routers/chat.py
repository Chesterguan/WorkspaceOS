import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, require_owned_project, verify_api_key
from app.models.chat import ChatMessage
from app.schemas.chat import (
    AdvisorInfo,
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatRoundtableResponse,
    ChatSendRequest,
)
from app.services import chat_service
from app.services.advisors import get_advisor_info_list
from app.services.chat_service import STRATEGIC_STARTERS

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["chat"])
starters_router = APIRouter(prefix="/chat", tags=["chat"])


def _to_response(msg: ChatMessage) -> ChatMessageResponse:
    """Convert a ChatMessage ORM object to response schema with advisor fields."""
    advisor_id = None
    advisor_name = None
    if msg.metadata_:
        advisor_id = msg.metadata_.get("advisor_id")
        advisor_name = msg.metadata_.get("advisor_name")
    return ChatMessageResponse(
        id=msg.id,
        project_id=msg.project_id,
        role=msg.role,
        content=msg.content,
        metadata_=msg.metadata_,
        created_at=msg.created_at,
        advisor_id=advisor_id,
        advisor_name=advisor_name,
    )


@router.post("", response_model=ChatRoundtableResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    project_id: uuid.UUID,
    body: ChatSendRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> ChatRoundtableResponse:
    """Send a message to the Co-Founder roundtable and receive advisor replies."""
    await require_owned_project(project_id, db, jwt_user_id)
    messages, routed_ids, group = await chat_service.send_message(
        project_id=project_id,
        user_message=body.message,
        include_workspace=body.include_workspace,
        include_memory=body.include_memory,
        include_repo=body.include_repo,
        advisor_id=body.advisor_id,
        db=db,
    )
    return ChatRoundtableResponse(
        messages=[_to_response(m) for m in messages],
        routed_advisors=routed_ids,
        roundtable_group=group,
    )


@router.get("", response_model=ChatHistoryResponse)
async def get_history(
    project_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> ChatHistoryResponse:
    """Retrieve paginated chat history for the project (oldest-first)."""
    await require_owned_project(project_id, db, jwt_user_id)
    messages, total = await chat_service.get_history(project_id, db, limit=limit, offset=offset)
    return ChatHistoryResponse(
        messages=[_to_response(m) for m in messages],
        total=total,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> None:
    """Delete all chat messages for the project."""
    await require_owned_project(project_id, db, jwt_user_id)
    await chat_service.clear_history(project_id, db)


@starters_router.get("/starters")
async def get_starters(
    _key: str = Depends(verify_api_key),
) -> List[dict]:
    """Return grouped strategic conversation starters."""
    return STRATEGIC_STARTERS


@starters_router.get("/advisors", response_model=List[AdvisorInfo])
async def get_advisors(
    _key: str = Depends(verify_api_key),
) -> List[dict]:
    """Return all advisor configs (no system prompts) for the frontend advisor picker."""
    return get_advisor_info_list()
