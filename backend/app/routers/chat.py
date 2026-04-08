import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.chat import ChatMessage
from app.models.project import Project
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


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


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
) -> ChatRoundtableResponse:
    """Send a message to the Co-Founder roundtable and receive advisor replies."""
    await _require_project(project_id, db)
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
) -> ChatHistoryResponse:
    """Retrieve paginated chat history for the project (oldest-first)."""
    await _require_project(project_id, db)
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
) -> None:
    """Delete all chat messages for the project."""
    await _require_project(project_id, db)
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
