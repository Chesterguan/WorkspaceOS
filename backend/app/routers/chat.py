import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.chat import ChatMessage
from app.models.project import Project
from app.schemas.chat import ChatHistoryResponse, ChatMessageResponse, ChatSendRequest
from app.services import chat_service

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["chat"])


async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("", response_model=ChatMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    project_id: uuid.UUID,
    body: ChatSendRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ChatMessage:
    """Send a message to the Co-Founder AI and receive a reply."""
    await _require_project(project_id, db)
    return await chat_service.send_message(
        project_id=project_id,
        user_message=body.message,
        include_workspace=body.include_workspace,
        include_memory=body.include_memory,
        include_repo=body.include_repo,
        db=db,
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
    return ChatHistoryResponse(messages=messages, total=total)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> None:
    """Delete all chat messages for the project."""
    await _require_project(project_id, db)
    await chat_service.clear_history(project_id, db)
