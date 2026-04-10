"""
Blog module router: full CRUD for blog posts, version history, and AI generation.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, get_optional_user_id, require_owned_project, verify_api_key
from app.models.blog import BlogPost, BlogPostVersion
from app.schemas.blog import (
    BlogGenerateRequest,
    BlogPostCreate,
    BlogPostResponse,
    BlogPostUpdate,
    BlogPostVersionResponse,
)
from app.services.blog_service import (
    create_blog_post,
    generate_blog_draft,
    get_version_chain,
    update_blog_post,
)

router = APIRouter(prefix="/projects", tags=["blog"])


async def _require_post(
    project_id: uuid.UUID,
    post_id: uuid.UUID,
    db: AsyncSession,
) -> BlogPost:
    result = await db.execute(
        select(BlogPost).where(BlogPost.id == post_id, BlogPost.project_id == project_id)
    )
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
    return post


@router.post(
    "/{project_id}/blog",
    response_model=BlogPostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_post(
    project_id: uuid.UUID,
    body: BlogPostCreate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> BlogPost:
    await require_owned_project(project_id, db, jwt_user_id)
    return await create_blog_post(project_id, body, db)


@router.get("/{project_id}/blog", response_model=List[BlogPostResponse])
async def list_posts(
    project_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    tag: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> List[BlogPost]:
    await require_owned_project(project_id, db, jwt_user_id)

    query = (
        select(BlogPost)
        .where(BlogPost.project_id == project_id)
        .order_by(BlogPost.created_at.desc())
    )
    if status_filter:
        query = query.where(BlogPost.status == status_filter)
    if tag:
        # PostgreSQL ARRAY contains operator via raw SQL text expression
        from sqlalchemy import text as sa_text
        query = query.where(
            BlogPost.tags.contains([tag])
        )

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{project_id}/blog/{post_id}", response_model=BlogPostResponse)
async def get_post(
    project_id: uuid.UUID,
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> BlogPost:
    await require_owned_project(project_id, db, jwt_user_id)
    return await _require_post(project_id, post_id, db)


@router.patch("/{project_id}/blog/{post_id}", response_model=BlogPostResponse)
async def update_post(
    project_id: uuid.UUID,
    post_id: uuid.UUID,
    body: BlogPostUpdate,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> BlogPost:
    await require_owned_project(project_id, db, jwt_user_id)
    await _require_post(project_id, post_id, db)
    return await update_blog_post(post_id, body, db)


@router.delete(
    "/{project_id}/blog/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_post(
    project_id: uuid.UUID,
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> None:
    await require_owned_project(project_id, db, jwt_user_id)
    post = await _require_post(project_id, post_id, db)
    await db.delete(post)
    await db.flush()


@router.get(
    "/{project_id}/blog/{post_id}/versions",
    response_model=List[BlogPostVersionResponse],
)
async def list_versions(
    project_id: uuid.UUID,
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> List[BlogPostVersion]:
    await require_owned_project(project_id, db, jwt_user_id)
    await _require_post(project_id, post_id, db)
    return await get_version_chain(post_id, db)


@router.get(
    "/{project_id}/blog/{post_id}/versions/{version_id}",
    response_model=BlogPostVersionResponse,
)
async def get_version(
    project_id: uuid.UUID,
    post_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> BlogPostVersion:
    await require_owned_project(project_id, db, jwt_user_id)
    await _require_post(project_id, post_id, db)

    result = await db.execute(
        select(BlogPostVersion).where(
            BlogPostVersion.id == version_id,
            BlogPostVersion.blog_post_id == post_id,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return version


@router.post(
    "/{project_id}/blog/{post_id}/generate",
    response_model=BlogPostResponse,
)
async def generate_post(
    project_id: uuid.UUID,
    post_id: uuid.UUID,
    body: BlogGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> BlogPost:
    """AI-generate blog content for an existing post, replacing its current content."""
    await require_owned_project(project_id, db, jwt_user_id)
    await _require_post(project_id, post_id, db)

    try:
        await generate_blog_draft(project_id, post_id, body.context_hint, db)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # Re-fetch and return the updated post
    result = await db.execute(select(BlogPost).where(BlogPost.id == post_id))
    return result.scalar_one()
