"""
Deep repository context extraction service.

Goes far beyond README — reads the actual codebase structure, key config files,
recent PRs, issues, CI setup, and package dependencies to build a comprehensive
understanding of what the project is, how it's built, and where it's heading.

Privacy-aware:
  - Public repos: full context sent to cloud AI
  - Private repos: fetched via GitHub API, summarized by LOCAL model,
    only the summary reaches cloud AI
"""
import logging
import time
from typing import Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.services.ai_client import get_local_client

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ---------------------------------------------------------------------------
# In-process TTL cache for repo context (avoids redundant GitHub API calls)
# ---------------------------------------------------------------------------

_context_cache: Dict[str, Tuple[float, str]] = {}
_CACHE_TTL = 600  # 10 minutes

# ---------------------------------------------------------------------------
# Reused HTTP client (avoid creating a new TCP connection on every call)
# ---------------------------------------------------------------------------

_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=15.0)
    return _http_client

# Files that reveal project architecture and purpose
KEY_FILES = [
    "package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml",
    "Gemfile", "build.gradle", "setup.py", "setup.cfg", "requirements.txt",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
    ".github/workflows/ci.yml", ".github/workflows/ci.yaml",
    ".github/workflows/main.yml", ".github/workflows/build.yml",
    "Makefile", "justfile",
    "CHANGELOG.md", "CHANGES.md", "HISTORY.md",
    "CONTRIBUTING.md", "ARCHITECTURE.md",
    "tsconfig.json", "next.config.js", "next.config.ts", "next.config.mjs",
    "vite.config.ts", "webpack.config.js",
    "alembic.ini", "prisma/schema.prisma",
]


def _headers() -> Dict[str, str]:
    return {**GITHUB_HEADERS, "Authorization": f"Bearer {settings.github_token}"}


async def _fetch_json(url: str, params: Optional[Dict] = None) -> Optional[object]:
    try:
        resp = await _get_http_client().get(url, params=params or {}, headers=_headers())
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug("GitHub API fetch failed for %s: %s", url, e)
    return None


async def _fetch_text(url: str) -> Optional[str]:
    try:
        headers = {**_headers(), "Accept": "application/vnd.github.raw+json"}
        resp = await _get_http_client().get(url, headers=headers)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.debug("GitHub API raw fetch failed for %s: %s", url, e)
    return None


async def _fetch_file_content(owner_repo: str, path: str) -> Optional[str]:
    """Fetch raw file content from repo. Returns None if file doesn't exist."""
    return await _fetch_text(f"{GITHUB_API}/repos/{owner_repo}/contents/{path}")


async def _fetch_directory_tree(owner_repo: str, path: str = "", depth: int = 0, max_depth: int = 2) -> List[str]:
    """Recursively fetch directory tree up to max_depth."""
    if depth > max_depth:
        return []
    data = await _fetch_json(f"{GITHUB_API}/repos/{owner_repo}/contents/{path}")
    if not data or not isinstance(data, list):
        return []
    items = []
    indent = "  " * depth
    dirs_to_recurse = []
    for item in sorted(data, key=lambda x: (x.get("type") != "dir", x.get("name", ""))):
        name = item.get("name", "")
        if name.startswith(".") and depth > 0:
            continue  # skip hidden files in subdirs
        if item.get("type") == "dir":
            items.append(f"{indent}{name}/")
            # Recurse into important directories
            if name in ("src", "app", "lib", "pkg", "cmd", "internal", "api",
                        "components", "pages", "routes", "services", "models",
                        "backend", "frontend", "server", "client", "core",
                        "modules", "packages", "crates"):
                dirs_to_recurse.append(item.get("path", name))
        else:
            items.append(f"{indent}{name}")
    for dir_path in dirs_to_recurse:
        sub_items = await _fetch_directory_tree(owner_repo, dir_path, depth + 1, max_depth)
        items.extend(sub_items)
    return items


async def fetch_repo_context(github_repo: str) -> Dict[str, str]:
    """
    Deep fetch of repository context. Gathers:
      - Repo metadata (description, stars, language, topics)
      - Full README
      - Deep directory tree (2 levels into key dirs)
      - Key config files (package.json, pyproject.toml, Dockerfile, CI, etc.)
      - Recent commits with full messages (not just first line)
      - Recent PRs (titles + descriptions)
      - Open issues (titles)
      - Release notes
      - Language breakdown
    """
    owner_repo = github_repo
    context: Dict[str, str] = {}

    # 1. Repo metadata
    repo_data = await _fetch_json(f"{GITHUB_API}/repos/{owner_repo}")
    if repo_data and isinstance(repo_data, dict):
        context["description"] = repo_data.get("description") or ""
        context["is_private"] = str(repo_data.get("private", False))
        context["stars"] = str(repo_data.get("stargazers_count", 0))
        context["forks"] = str(repo_data.get("forks_count", 0))
        context["language"] = repo_data.get("language") or ""
        context["created_at"] = repo_data.get("created_at", "")
        context["updated_at"] = repo_data.get("pushed_at", "")
        context["default_branch"] = repo_data.get("default_branch", "main")
        topics = repo_data.get("topics") or []
        context["topics"] = ", ".join(topics) if topics else ""
        context["homepage"] = repo_data.get("homepage") or ""
        context["license"] = (repo_data.get("license") or {}).get("spdx_id", "") if isinstance(repo_data.get("license"), dict) else ""

    # 2. README (full)
    readme = await _fetch_text(f"{GITHUB_API}/repos/{owner_repo}/readme")
    context["readme"] = readme or ""

    # 3. Deep directory tree
    tree_items = await _fetch_directory_tree(owner_repo, "", 0, 2)
    context["file_tree"] = "\n".join(tree_items) if tree_items else ""

    # 4. Key config files
    config_contents: List[str] = []
    for filepath in KEY_FILES:
        content = await _fetch_file_content(owner_repo, filepath)
        if content:
            # Truncate very large config files
            if len(content) > 2000:
                content = content[:2000] + "\n... (truncated)"
            config_contents.append(f"### {filepath}\n```\n{content}\n```")
    context["key_configs"] = "\n\n".join(config_contents) if config_contents else ""

    # 5. Recent commits (last 30, with full first paragraph of message)
    commits_data = await _fetch_json(
        f"{GITHUB_API}/repos/{owner_repo}/commits",
        params={"per_page": "30"},
    )
    if commits_data and isinstance(commits_data, list):
        lines = []
        for c in commits_data:
            full_msg = c.get("commit", {}).get("message", "")
            # Take first paragraph (up to first double newline)
            msg = full_msg.split("\n\n")[0].replace("\n", " ").strip()
            if len(msg) > 200:
                msg = msg[:200] + "..."
            sha = c.get("sha", "")[:7]
            date = c.get("commit", {}).get("author", {}).get("date", "")[:10]
            author = c.get("commit", {}).get("author", {}).get("name", "")
            lines.append(f"- [{date}] {sha} ({author}): {msg}")
        context["recent_commits"] = "\n".join(lines)
    else:
        context["recent_commits"] = ""

    # 6. Recent PRs (last 10, merged + open)
    prs_data = await _fetch_json(
        f"{GITHUB_API}/repos/{owner_repo}/pulls",
        params={"state": "all", "per_page": "10", "sort": "updated", "direction": "desc"},
    )
    if prs_data and isinstance(prs_data, list):
        pr_lines = []
        for pr in prs_data:
            state = pr.get("state", "")
            merged = pr.get("merged_at") is not None
            status = "merged" if merged else state
            title = pr.get("title", "")
            body = (pr.get("body") or "")[:300]
            pr_lines.append(f"- [{status}] #{pr.get('number', '?')}: {title}")
            if body.strip():
                pr_lines.append(f"  {body.strip()}")
        context["recent_prs"] = "\n".join(pr_lines)
    else:
        context["recent_prs"] = ""

    # 7. Open issues (last 10)
    issues_data = await _fetch_json(
        f"{GITHUB_API}/repos/{owner_repo}/issues",
        params={"state": "open", "per_page": "10", "sort": "updated"},
    )
    if issues_data and isinstance(issues_data, list):
        # Filter out PRs (GitHub API returns PRs as issues too)
        issue_lines = []
        for issue in issues_data:
            if issue.get("pull_request"):
                continue
            labels = ", ".join(l.get("name", "") for l in (issue.get("labels") or []))
            title = issue.get("title", "")
            line = f"- #{issue.get('number', '?')}: {title}"
            if labels:
                line += f" [{labels}]"
            issue_lines.append(line)
        context["open_issues"] = "\n".join(issue_lines) if issue_lines else ""
    else:
        context["open_issues"] = ""

    # 8. Recent releases (last 3)
    releases_data = await _fetch_json(
        f"{GITHUB_API}/repos/{owner_repo}/releases",
        params={"per_page": "3"},
    )
    if releases_data and isinstance(releases_data, list):
        release_lines = []
        for rel in releases_data:
            tag = rel.get("tag_name", "")
            name = rel.get("name", "")
            body = (rel.get("body") or "")[:500]
            date = (rel.get("published_at") or "")[:10]
            release_lines.append(f"### {tag} — {name} ({date})")
            if body:
                release_lines.append(body)
        context["releases"] = "\n\n".join(release_lines)
    else:
        context["releases"] = ""

    # 9. Languages breakdown
    langs_data = await _fetch_json(f"{GITHUB_API}/repos/{owner_repo}/languages")
    if langs_data and isinstance(langs_data, dict):
        total = sum(langs_data.values())
        if total > 0:
            parts = []
            for lang, bytes_count in sorted(langs_data.items(), key=lambda x: -x[1]):
                pct = round(bytes_count / total * 100, 1)
                parts.append(f"{lang} ({pct}%)")
            context["languages"] = ", ".join(parts)
        else:
            context["languages"] = ""
    else:
        context["languages"] = ""

    return context


def format_context_block(ctx: Dict[str, str]) -> str:
    """Format fetched repo context into a comprehensive text block for prompts."""
    sections = []

    # Project identity
    meta_parts = []
    if ctx.get("description"):
        meta_parts.append(f"Description: {ctx['description']}")
    if ctx.get("language"):
        meta_parts.append(f"Primary language: {ctx['language']}")
    if ctx.get("stars") and ctx["stars"] != "0":
        meta_parts.append(f"Stars: {ctx['stars']}")
    if ctx.get("license"):
        meta_parts.append(f"License: {ctx['license']}")
    if ctx.get("topics"):
        meta_parts.append(f"Topics: {ctx['topics']}")
    if ctx.get("homepage"):
        meta_parts.append(f"Homepage: {ctx['homepage']}")
    if meta_parts:
        sections.append("## Project Identity\n" + "\n".join(meta_parts))

    # Tech stack
    if ctx.get("languages"):
        sections.append(f"## Tech Stack\n{ctx['languages']}")

    # README — the most important piece
    if ctx.get("readme"):
        readme = ctx["readme"]
        if len(readme) > 6000:
            readme = readme[:6000] + "\n\n[... truncated ...]"
        sections.append(f"## README\n{readme}")

    # Project structure
    if ctx.get("file_tree"):
        sections.append(f"## Project Structure\n{ctx['file_tree']}")

    # Key configuration files
    if ctx.get("key_configs"):
        configs = ctx["key_configs"]
        if len(configs) > 4000:
            configs = configs[:4000] + "\n\n[... truncated ...]"
        sections.append(f"## Key Configuration Files\n{configs}")

    # Recent development activity
    if ctx.get("recent_commits"):
        sections.append(f"## Recent Commits (last 30)\n{ctx['recent_commits']}")

    # PRs show what the team is working on
    if ctx.get("recent_prs"):
        sections.append(f"## Recent Pull Requests\n{ctx['recent_prs']}")

    # Issues show what users care about and what's planned
    if ctx.get("open_issues"):
        sections.append(f"## Open Issues\n{ctx['open_issues']}")

    # Releases show the public-facing narrative
    if ctx.get("releases"):
        sections.append(f"## Recent Releases\n{ctx['releases']}")

    return "\n\n".join(sections)


async def get_generation_context(
    github_repo: str,
    is_private: bool = False,
) -> str:
    """
    Main entry point. Deep-fetches repo context with a 10-minute TTL cache.

    Public repos: returns full raw context for cloud AI.
    Private repos: fetches everything, then LOCAL model produces a
    comprehensive summary — raw private data never leaves your machine.
    """
    cache_key = f"{github_repo}:{is_private}"
    now = time.time()
    if cache_key in _context_cache:
        cached_time, cached_result = _context_cache[cache_key]
        if now - cached_time < _CACHE_TTL:
            logger.debug("repo_context cache hit for %s", github_repo)
            return cached_result

    raw_context = await fetch_repo_context(github_repo)
    formatted = format_context_block(raw_context)

    if not formatted.strip():
        return "No repository context available."

    if is_private:
        local = get_local_client()
        try:
            summary = await local.complete(
                "You are a senior developer analyzing a codebase. Produce a comprehensive "
                "project briefing from the following repository data. Cover:\n"
                "1. What the project does and who it's for\n"
                "2. Architecture and tech stack (frameworks, languages, key dependencies)\n"
                "3. Project maturity and development velocity\n"
                "4. Recent focus areas (from commits, PRs, issues)\n"
                "5. Key features and capabilities\n"
                "6. Anything notable or unique about the project\n\n"
                "Write 4-6 detailed paragraphs. Be specific — cite actual file names, "
                "dependencies, and commit messages. Do NOT include any API keys, tokens, "
                "internal URLs, passwords, or sensitive credentials.",
                f"Repository data:\n\n{formatted}",
            )
            result = f"## Repository Deep Context (summarized for privacy)\n{summary}"
            _context_cache[cache_key] = (now, result)
            return result
        except Exception as e:
            logger.warning("Local model summarization failed: %s", e)
            safe_parts = []
            if raw_context.get("description"):
                safe_parts.append(f"Description: {raw_context['description']}")
            if raw_context.get("languages"):
                safe_parts.append(f"Languages: {raw_context['languages']}")
            if raw_context.get("topics"):
                safe_parts.append(f"Topics: {raw_context['topics']}")
            return "\n".join(safe_parts) if safe_parts else "No repository context available."

    _context_cache[cache_key] = (now, formatted)
    return formatted
