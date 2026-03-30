from typing import List, Optional

from pydantic import BaseModel, Field


class GitHubRepoResponse(BaseModel):
    """Represents a single GitHub repository returned by the listing endpoint."""

    full_name: str
    name: str
    description: Optional[str]
    default_branch: str
    html_url: str
    updated_at: Optional[str]
    stargazers_count: int
    language: Optional[str]
    fork: bool
    owner_login: str


class RepoImportItem(BaseModel):
    """A single repo selected by the user for import."""

    full_name: str = Field(
        ...,
        description="owner/repo format",
        examples=["octocat/Hello-World"],
    )
    # name is optional; if omitted it is derived from full_name (the part after '/')
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    default_branch: str = Field(default="main", max_length=100, examples=["main"])


class RepoImportRequest(BaseModel):
    """
    Request body for POST /github/repos/import.

    Example::

        {"repos": [{"full_name": "owner/repo", "default_branch": "main"}]}
    """

    repos: List[RepoImportItem] = Field(
        ...,
        min_length=1,
        examples=[[{"full_name": "octocat/Hello-World", "default_branch": "main"}]],
    )
    # user_id is optional; if omitted the router falls back to the first user in the DB
    user_id: Optional[str] = Field(default=None, description="UUID of the owning user")


class RepoImportResponse(BaseModel):
    """Response after a bulk repo import."""

    created: List[str] = Field(default_factory=list, description="Slugs of newly created projects")
    skipped: List[str] = Field(default_factory=list, description="Slugs that already existed")
