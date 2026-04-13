"""
GitHub repo selector router.
Lists and imports the authenticated user's GitHub repos as projects.
"""
import os
import re
import time
import uuid
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import (
    get_db,
    get_optional_user_id,
    require_owned_project,
    verify_api_key,
)
from app.models.project import Project
from app.models.user import User
from app.schemas.github import GitHubRepoResponse, RepoImportRequest, RepoImportResponse
from app.services.github_client import GitHubClient

router = APIRouter(prefix="/github", tags=["github"])

# In-memory cache for the branches endpoint: { (user_id, repo) -> (expires_at, list) }
# Branches are listed relatively often from the UI; caching for 5 minutes keeps
# the GitHub API rate limit happy without serving stale data for long.
_BRANCHES_CACHE_TTL_SEC = 300
_branches_cache: Dict[Tuple[str, str], Tuple[float, List[dict]]] = {}


def _repo_name_to_slug(name: str) -> str:
    """
    Derive a URL-safe slug from a GitHub repo name.
    Lowercases, replaces non-alphanumeric characters with hyphens, and
    strips leading/trailing hyphens.
    """
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "repo"


@router.get("/status", summary="Check GitHub connection status")
async def github_status(
    _key: str = Depends(verify_api_key),
) -> dict:
    """
    Verify that a GitHub token is configured and return the authenticated
    username by calling GET https://api.github.com/user.

    Response: { connected: bool, username: str }
    """
    if not settings.github_token:
        return {"connected": False, "username": ""}

    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {settings.github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"connected": True, "username": data.get("login", "")}
            return {"connected": False, "username": ""}
    except Exception:
        return {"connected": False, "username": ""}


@router.get("/repos", response_model=List[GitHubRepoResponse])
async def list_github_repos(
    _key: str = Depends(verify_api_key),
) -> List[dict]:
    """
    Fetch all non-fork repos owned by the demo user via their stored GitHub token.
    Uses the global github_token from settings (the demo user's token).
    """
    if not settings.github_token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No GitHub token configured. Set GITHUB_TOKEN in the environment.",
        )
    client = GitHubClient(token=settings.github_token)
    try:
        repos = await client.fetch_all_repos()
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return repos


@router.post("/repos/import", response_model=RepoImportResponse, status_code=status.HTTP_201_CREATED)
async def import_repos(
    body: RepoImportRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> RepoImportResponse:
    """
    Create projects from a list of selected GitHub repos.

    Ownership resolution (first match wins):
      1. JWT user from ``Authorization: Bearer`` header
      2. Explicit ``body.user_id``
      3. First user in the DB (admin / script / seed mode)

    Derives the slug from the repo name. Skips repos whose slug already exists
    for this user. Returns lists of created and skipped slugs.
    """
    if jwt_user_id is not None:
        try:
            user_id = uuid.UUID(jwt_user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user id in token",
            )
    elif body.user_id is not None:
        try:
            user_id = uuid.UUID(body.user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid user_id: '{body.user_id}'",
            )
        user_result = await db.execute(select(User).where(User.id == user_id))
        if user_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found",
            )
    else:
        user_result = await db.execute(select(User).order_by(User.created_at.asc()).limit(1))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No users exist in the database. Provide a user_id or run the seed script.",
            )
        user_id = user.id

    created: List[str] = []
    skipped: List[str] = []

    for repo_item in body.repos:
        # Derive name from full_name when not explicitly provided
        repo_name = repo_item.name or repo_item.full_name.split("/")[-1]
        slug = _repo_name_to_slug(repo_name)

        # Check for existing project with this slug under the same user
        existing = await db.execute(
            select(Project).where(
                Project.user_id == user_id,
                Project.slug == slug,
            )
        )
        if existing.scalar_one_or_none() is not None:
            skipped.append(slug)
            continue

        # Only wire up a local_path when the repo actually exists at the
        # Docker volume mount — otherwise leave it NULL so the workspace
        # scanner falls back to the remote repo_cache path. Previously this
        # hard-coded a fake path like /projects/<name>, which broke every
        # feature that expected a real directory.
        candidate_local = f"/projects/{repo_name}"
        local_path = candidate_local if os.path.isdir(candidate_local) else None

        project = Project(
            user_id=user_id,
            name=repo_name,
            slug=slug,
            description=repo_item.description,
            github_repo=repo_item.full_name,
            github_branch=repo_item.default_branch,
            github_full_name=repo_item.full_name,
            local_path=local_path,
            status="active",
        )
        db.add(project)
        await db.flush()
        created.append(slug)

    return RepoImportResponse(created=created, skipped=skipped)


@router.get(
    "/projects/{project_id}/branches",
    summary="List branches of the GitHub repo linked to a project",
)
async def list_project_branches(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
    jwt_user_id: Optional[str] = Depends(get_optional_user_id),
) -> List[dict]:
    """
    Return the list of branches for `project.github_repo` via the GitHub REST
    API. Each item is { name, is_default, commit_sha }. Results are cached in
    memory for 5 minutes per (user, repo) to avoid hammering GitHub every time
    the branch picker is opened.
    """
    project = await require_owned_project(project_id, db, jwt_user_id)

    if not project.github_repo:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Project has no github_repo set; cannot list branches.",
        )
    if not settings.github_token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No GitHub token configured.",
        )

    cache_key = (str(project.user_id), project.github_repo)
    now = time.monotonic()
    cached = _branches_cache.get(cache_key)
    if cached is not None and cached[0] > now:
        return cached[1]

    default_branch = project.github_branch or "main"
    branches: List[dict] = []

    import httpx
    url = f"https://api.github.com/repos/{project.github_repo}/branches"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            page = 1
            while True:
                resp = await client.get(
                    url,
                    params={"per_page": 100, "page": page},
                    headers={
                        "Authorization": f"Bearer {settings.github_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
                if resp.status_code == 404:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"GitHub repo '{project.github_repo}' not found.",
                    )
                if resp.status_code == 401:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="GitHub token is invalid or expired.",
                    )
                resp.raise_for_status()
                rows = resp.json()
                for row in rows:
                    name = row.get("name", "")
                    branches.append({
                        "name": name,
                        "is_default": name == default_branch,
                        "commit_sha": (row.get("commit") or {}).get("sha", ""),
                    })
                # GitHub returns fewer than 100 on the last page
                if len(rows) < 100:
                    break
                page += 1
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch branches from GitHub: {exc}",
        )

    # Sort: default first, then alphabetical
    branches.sort(key=lambda b: (not b["is_default"], b["name"]))

    _branches_cache[cache_key] = (now + _BRANCHES_CACHE_TTL_SEC, branches)
    return branches
