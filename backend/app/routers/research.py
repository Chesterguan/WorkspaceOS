"""
Research Assistant router.

Endpoints:
  POST   /projects/{project_id}/research          — send message, get AI reply
  GET    /projects/{project_id}/research          — paginated research history
  DELETE /projects/{project_id}/research          — clear research history
  GET    /research/starters                       — grouped conversation starters
  POST   /projects/{project_id}/research/search-papers — direct Semantic Scholar search
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.models.chat import ChatMessage
from app.models.project import Project
from app.schemas.research import (
    PaperResult,
    PaperSearchRequest,
    PaperSearchResponse,
    ResearchHistoryResponse,
    ResearchMessageRequest,
    ResearchMessageResponse,
)
from app.services import research_service
from app.services.research_service import RESEARCH_STARTERS
from app.services.scholar_service import (
    format_paper_citation,
    search_papers,
)

router = APIRouter(prefix="/projects/{project_id}/research", tags=["research"])

# Separate router for non-project-scoped research endpoints
starters_router = APIRouter(prefix="/research", tags=["research"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_project(project_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _paper_dict_to_result(paper: dict) -> PaperResult:
    """Convert a raw Semantic Scholar paper dict to a PaperResult schema."""
    authors_raw = paper.get("authors") or []
    author_names: List[str] = []
    for a in authors_raw:
        if isinstance(a, dict):
            name = a.get("name", "")
            if name:
                author_names.append(name)
        elif isinstance(a, str):
            author_names.append(a)

    ext_ids = paper.get("externalIds") or {}
    doi = ext_ids.get("DOI")

    return PaperResult(
        paper_id=paper.get("paperId") or "",
        title=paper.get("title") or "Untitled",
        authors=author_names,
        year=paper.get("year"),
        abstract=paper.get("abstract"),
        citation_count=paper.get("citationCount") or 0,
        url=paper.get("url"),
        doi=doi,
        citation_string=format_paper_citation(paper),
    )


# ---------------------------------------------------------------------------
# Project-scoped endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=ResearchMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_research_message(
    project_id: uuid.UUID,
    body: ResearchMessageRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ChatMessage:
    """
    Send a message to the Research Assistant and receive a citation-backed reply.

    The assistant searches Semantic Scholar for related papers and uses them
    to ground its response. All messages are stored in the database.
    """
    await _require_project(project_id, db)
    return await research_service.send_research_message(
        project_id=project_id,
        user_message=body.message,
        include_literature=body.include_literature,
        include_workspace=body.include_workspace,
        include_repo=body.include_repo,
        db=db,
    )


@router.get("", response_model=ResearchHistoryResponse)
async def get_research_history(
    project_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ResearchHistoryResponse:
    """Retrieve paginated research conversation history (oldest-first)."""
    await _require_project(project_id, db)
    messages, total = await research_service.get_research_history(
        project_id, db, limit=limit, offset=offset
    )
    return ResearchHistoryResponse(messages=messages, total=total)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_research_history(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> None:
    """Delete all research messages for the project. Co-founder chat is unaffected."""
    await _require_project(project_id, db)
    await research_service.clear_research_history(project_id, db)


@router.post(
    "/search-papers",
    response_model=PaperSearchResponse,
    status_code=status.HTTP_200_OK,
)
async def search_papers_endpoint(
    project_id: uuid.UUID,
    body: PaperSearchRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaperSearchResponse:
    """
    Direct Semantic Scholar paper search for the given query.

    Returns structured paper results including pre-formatted citation strings.
    Useful for building a bibliography or exploring the literature landscape.
    """
    await _require_project(project_id, db)
    raw_papers = await search_papers(body.query, limit=body.limit)
    results = [_paper_dict_to_result(p) for p in raw_papers]
    return PaperSearchResponse(
        papers=results,
        query=body.query,
        total=len(results),
    )


# ---------------------------------------------------------------------------
# Non-project-scoped endpoints
# ---------------------------------------------------------------------------

@starters_router.get("/starters")
async def get_research_starters(
    _key: str = Depends(verify_api_key),
) -> List[dict]:
    """Return grouped research conversation starters."""
    return RESEARCH_STARTERS
