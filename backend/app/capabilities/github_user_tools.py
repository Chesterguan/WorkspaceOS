"""github_user_tools ingest_source — personal GitHub repo catalog.

Pulls public repos for one or more GitHub usernames and creates one
`tool` knowledge node per repo. Designed to let the research panel and
(in a later release) `/draft_methods` cite tools you've actually
authored, rather than pulling from a generic registry.

Config:
    usernames:              list of GitHub handles to track
    token:                  optional GitHub personal access token
                            (unauthenticated = 60 req/h; token = 5000/h)
    include_forks:          false — forks are usually not authored work
    include_archived:       false — archived repos rarely "active tools"
    max_repos_per_user:     50 — cap to prevent floods
    poll_interval_seconds:  86400 — 24 h; repos don't change fast

Missing usernames = graceful no-op + warn-level event.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.capabilities.base import IngestContext, IngestSource

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_USER_AGENT = "WorkspaceOS/0.2"
_README_CAP = 4000   # characters


def _base_headers(token: str) -> Dict[str, str]:
    """Build GitHub API request headers. Token is optional."""
    headers: Dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": _USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class GitHubUserTools(IngestSource):
    """Catalogs a user's public GitHub repos as `tool` knowledge nodes."""

    label = "github-user-tools"
    default_poll_interval_seconds = 86400  # 24 h

    async def run(self, config: Dict[str, Any], ctx: IngestContext) -> int:
        usernames: List[str] = [
            u.strip() for u in (config.get("usernames") or []) if u.strip()
        ]
        if not usernames:
            ctx.log("warn", "github-user-tools: no usernames configured — skipping")
            return 0

        token = str(config.get("token") or "").strip()
        include_forks = bool(config.get("include_forks", False))
        include_archived = bool(config.get("include_archived", False))
        max_repos = int(config.get("max_repos_per_user") or 50)

        headers = _base_headers(token)
        ingested = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            for username in usernames:
                try:
                    count = await self._ingest_user(
                        client=client,
                        username=username,
                        headers=headers,
                        include_forks=include_forks,
                        include_archived=include_archived,
                        max_repos=max_repos,
                        ctx=ctx,
                    )
                    ingested += count
                except Exception as exc:
                    ctx.log("error", f"github-user-tools: error for {username} — {exc}")
                    logger.exception("github-user-tools: unexpected error for %s", username)

        if ingested:
            ctx.log("success", f"github-user-tools: pulled {ingested} new tool nodes")
        else:
            logger.debug("github-user-tools: no new repos this tick")
        return ingested

    async def _ingest_user(
        self,
        *,
        client: httpx.AsyncClient,
        username: str,
        headers: Dict[str, str],
        include_forks: bool,
        include_archived: bool,
        max_repos: int,
        ctx: IngestContext,
    ) -> int:
        repos = await _fetch_repos(client, username, headers, max_repos)
        if repos is None:
            # _fetch_repos already logged via ctx; return 0 here.
            return 0

        ingested = 0
        for repo in repos:
            try:
                # Apply filters before touching the README endpoint.
                if not include_forks and repo.get("fork"):
                    continue
                if not include_archived and repo.get("archived"):
                    continue

                full_name: str = repo.get("full_name") or ""
                name: str = repo.get("name") or full_name
                description: str = repo.get("description") or ""
                language: str = repo.get("language") or ""
                html_url: str = repo.get("html_url") or ""
                stars: int = repo.get("stargazers_count") or 0
                default_branch: str = repo.get("default_branch") or ""
                pushed_at: str = repo.get("pushed_at") or ""
                topics: List[str] = repo.get("topics") or []

                readme = await _fetch_readme(client, full_name, headers)

                content = _build_content(
                    full_name=full_name,
                    description=description,
                    language=language,
                    stars=stars,
                    html_url=html_url,
                    pushed_at=pushed_at,
                    readme=readme,
                )

                external_id = f"github:{full_name}"

                inserted = await ctx.upsert_node(
                    node_type="tool",
                    title=name[:160],
                    content=content,
                    external_id=external_id,
                    metadata={
                        "github_full_name": full_name,
                        "github_url": html_url,
                        "language": language,
                        "stars": stars,
                        "description": description,
                        "topics": topics,
                        "default_branch": default_branch,
                        "pushed_at": pushed_at,
                        "owner": username,
                    },
                )
                if inserted:
                    ingested += 1

            except Exception as exc:
                logger.warning(
                    "github-user-tools: skip repo %s — %s",
                    repo.get("full_name", "?"),
                    exc,
                )
                continue

        return ingested


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _fetch_repos(
    client: httpx.AsyncClient,
    username: str,
    headers: Dict[str, str],
    max_repos: int,
) -> Optional[List[Dict[str, Any]]]:
    """Fetch up to max_repos public repos for username.

    Returns None on HTTP error (caller should log + continue to next user).
    We cap at 100 per page (GitHub's maximum), one page only; callers
    requesting more would need pagination, but max_repos_per_user=50
    keeps us well within a single page.
    """
    per_page = min(max_repos, 100)
    try:
        resp = await client.get(
            f"{_GITHUB_API}/users/{username}/repos",
            headers=headers,
            params={
                "type": "public",
                "per_page": per_page,
                "sort": "pushed",
                "direction": "desc",
            },
        )
    except httpx.HTTPError as exc:
        logger.warning("github-user-tools: network error fetching repos for %s — %s", username, exc)
        return None

    if resp.status_code == 404:
        logger.warning("github-user-tools: user not found: %s", username)
        return []
    if resp.status_code == 403:
        logger.warning("github-user-tools: 403 for %s — rate limit or bad token", username)
        return None
    if resp.status_code != 200:
        logger.warning(
            "github-user-tools: %s returned %d — %s",
            username, resp.status_code, resp.text[:120],
        )
        return None

    repos: List[Dict[str, Any]] = resp.json() or []
    # Enforce our own cap in case the server sends more than expected.
    return repos[:max_repos]


async def _fetch_readme(
    client: httpx.AsyncClient,
    full_name: str,
    headers: Dict[str, str],
) -> str:
    """Fetch raw README text for a repo, capped at _README_CAP chars.

    Returns empty string if the repo has no README or the request fails.
    We swap the Accept header to get raw content back instead of base64.
    """
    raw_headers = dict(headers)
    raw_headers["Accept"] = "application/vnd.github.raw+json"
    try:
        resp = await client.get(
            f"{_GITHUB_API}/repos/{full_name}/readme",
            headers=raw_headers,
        )
    except httpx.HTTPError:
        return ""

    if resp.status_code != 200:
        # 404 = no README — expected and fine.
        return ""

    return resp.text[:_README_CAP]


def _build_content(
    *,
    full_name: str,
    description: str,
    language: str,
    stars: int,
    html_url: str,
    pushed_at: str,
    readme: str,
) -> str:
    """Assemble the knowledge node content block."""
    lines = [
        f"Repo: {full_name}",
        f"Description: {description or '—'}",
        f"Language: {language or '—'}",
        f"Stars: {stars}",
        f"URL: {html_url}",
        f"Last pushed: {pushed_at or '—'}",
    ]
    if readme:
        lines.append("")
        lines.append("README (truncated):")
        lines.append(readme)
    return "\n".join(lines)
