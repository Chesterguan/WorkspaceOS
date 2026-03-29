"""
GitHub API client for listing and paginating user repositories.
Used by the repo selector feature to let users import their repos as projects.
"""
from typing import Dict, List

import httpx


class GitHubClient:
    """Async client wrapping the GitHub REST API for repo discovery."""

    BASE_URL = "https://api.github.com"
    DEFAULT_HEADERS = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    def __init__(self, token: str) -> None:
        self._token = token

    def _headers(self) -> Dict[str, str]:
        return {**self.DEFAULT_HEADERS, "Authorization": f"Bearer {self._token}"}

    async def list_user_repos(self, page: int = 1, per_page: int = 100) -> List[dict]:
        """Fetch one page of the authenticated user's repos."""
        url = f"{self.BASE_URL}/user/repos"
        params = {
            "per_page": per_page,
            "page": page,
            "sort": "updated",
            "direction": "desc",
            # "affiliation" defaults to owner,collaborator,organization_member;
            # we filter to owner-only after fetching.
            "affiliation": "owner",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params, headers=self._headers())
            if response.status_code == 401:
                raise PermissionError("GitHub token is invalid or expired. Please update GITHUB_TOKEN.")
            response.raise_for_status()
            return response.json()

    async def fetch_all_repos(self) -> List[dict]:
        """
        Paginate through all pages and return only repos that are:
          - owned by the authenticated user (not a fork, not a collaborator repo)
        """
        all_repos: List[dict] = []
        page = 1
        per_page = 100

        while True:
            page_results = await self.list_user_repos(page=page, per_page=per_page)
            if not page_results:
                break

            # Filter to owner repos only, exclude forks
            for repo in page_results:
                owner = repo.get("owner", {})
                # Include only repos the user personally owns, not forks
                if not repo.get("fork", False):
                    all_repos.append({
                        "full_name": repo.get("full_name", ""),
                        "name": repo.get("name", ""),
                        "description": repo.get("description"),
                        "default_branch": repo.get("default_branch", "main"),
                        "html_url": repo.get("html_url", ""),
                        "updated_at": repo.get("updated_at"),
                        "stargazers_count": repo.get("stargazers_count", 0),
                        "language": repo.get("language"),
                        "fork": repo.get("fork", False),
                        "owner_login": owner.get("login", ""),
                    })

            # GitHub returns fewer than per_page items on the last page
            if len(page_results) < per_page:
                break
            page += 1

        return all_repos
