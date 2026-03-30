"""
Workspace scanner service.

Reads the local filesystem (mounted via Docker volume) to build a snapshot of
the project's current state: directory tree, git info, key config files, and
recently changed files.  A local AI model produces a concise summary so that
sensitive code never reaches cloud providers.
"""
import asyncio
import logging
import os
import subprocess
import uuid
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import WorkspaceSnapshot
from app.services.ai_client import get_local_client

logger = logging.getLogger(__name__)

# Files that signal project type and architecture
_KEY_FILENAMES = [
    "README.md", "README.rst", "README.txt",
    "package.json", "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "Cargo.toml", "go.mod", "pom.xml", "Gemfile", "build.gradle",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "justfile",
    "tsconfig.json", "next.config.js", "next.config.ts", "next.config.mjs",
    "vite.config.ts", "webpack.config.js",
    "alembic.ini", "prisma/schema.prisma",
    "CHANGELOG.md", "ARCHITECTURE.md", "CONTRIBUTING.md",
]

# Media file extensions to discover for post attachments
_MEDIA_EXTENSIONS = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    # Videos
    ".mp4", ".webm", ".mov", ".avi", ".mkv",
    # Animated
    ".gif",
    # Diagrams (source)
    ".mmd", ".mermaid", ".puml", ".plantuml",
}

# Directories likely to contain media assets
_MEDIA_DIRS = {
    "assets", "images", "img", "media", "screenshots", "docs",
    "static", "public", "resources", "figures", "demo", "examples",
}

# Directories to skip entirely when building the file tree
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", ".next", ".nuxt", "target", "vendor",
    ".venv", "venv", "env", ".env", ".tox",
}


def _run(cmd: List[str], cwd: str, timeout: int = 10) -> str:
    """Run a subprocess and return stdout, or an empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except Exception as e:
        logger.debug("Command %s failed in %s: %s", cmd, cwd, e)
        return ""


def _build_file_tree(root: str, max_depth: int = 2) -> str:
    """
    Walk the directory tree up to max_depth levels deep, skipping noise dirs.
    Returns a newline-joined string of paths relative to root.
    """
    lines: List[str] = []

    def _walk(path: str, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name))
        except PermissionError:
            return
        for entry in entries:
            if entry.name.startswith(".") and depth > 0:
                continue
            if entry.is_dir(follow_symlinks=False):
                if entry.name in _SKIP_DIRS:
                    continue
                lines.append(f"{prefix}{entry.name}/")
                _walk(entry.path, depth + 1, prefix + "  ")
            else:
                lines.append(f"{prefix}{entry.name}")

    _walk(root, 0, "")
    return "\n".join(lines)


def _read_key_files(root: str) -> str:
    """Read key config/documentation files and format them for inclusion in prompts."""
    sections: List[str] = []
    for rel_path in _KEY_FILENAMES:
        abs_path = os.path.join(root, rel_path)
        if not os.path.isfile(abs_path):
            continue
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            # Truncate very large files to keep the prompt manageable
            if len(content) > 2000:
                content = content[:2000] + "\n... (truncated)"
            sections.append(f"### {rel_path}\n```\n{content}\n```")
        except Exception as e:
            logger.debug("Could not read %s: %s", abs_path, e)
    return "\n\n".join(sections)


def _recent_changed_files(root: str) -> str:
    """Return a list of files changed in the last 10 git commits."""
    output = _run(
        ["git", "diff", "--name-only", "HEAD~10", "HEAD"],
        cwd=root,
    )
    if not output:
        # Fallback: files changed but not yet committed
        output = _run(["git", "diff", "--name-only"], cwd=root)
    return output


def _discover_media_assets(root: str) -> str:
    """
    Scan for media files (images, videos, GIFs, diagrams) that could be
    attached to social posts. Searches the root + known media directories.

    Returns a formatted string listing found assets with type, path, and size.
    """
    assets: List[Dict[str, str]] = []

    def _scan_dir(dirpath: str, rel_prefix: str = "") -> None:
        try:
            entries = os.scandir(dirpath)
        except (PermissionError, FileNotFoundError):
            return
        for entry in entries:
            if entry.is_file(follow_symlinks=False):
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in _MEDIA_EXTENSIONS:
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    rel_path = os.path.join(rel_prefix, entry.name) if rel_prefix else entry.name
                    # Categorize
                    if ext in (".mp4", ".webm", ".mov", ".avi", ".mkv"):
                        media_type = "video"
                    elif ext == ".gif":
                        media_type = "gif"
                    elif ext in (".svg", ".mmd", ".mermaid", ".puml", ".plantuml"):
                        media_type = "diagram"
                    else:
                        media_type = "image"
                    size_str = f"{size / 1024:.0f}KB" if size < 1024 * 1024 else f"{size / (1024*1024):.1f}MB"
                    assets.append({
                        "type": media_type,
                        "path": rel_path,
                        "size": size_str,
                        "name": entry.name,
                    })
            elif entry.is_dir(follow_symlinks=False) and entry.name in _MEDIA_DIRS:
                _scan_dir(entry.path, os.path.join(rel_prefix, entry.name) if rel_prefix else entry.name)

    # Scan root level files
    _scan_dir(root)

    # Also scan common subdirectories that might have media
    for subdir in _MEDIA_DIRS:
        sub_path = os.path.join(root, subdir)
        if os.path.isdir(sub_path):
            _scan_dir(sub_path, subdir)

    # Also check docs/ subdirectories recursively (up to 2 levels)
    for docs_dir in ("docs", "doc", "documentation"):
        docs_path = os.path.join(root, docs_dir)
        if os.path.isdir(docs_path):
            for sub_entry in os.scandir(docs_path):
                if sub_entry.is_dir(follow_symlinks=False):
                    _scan_dir(sub_entry.path, os.path.join(docs_dir, sub_entry.name))

    if not assets:
        return ""

    # Deduplicate by path
    seen = set()
    unique = []
    for a in assets:
        if a["path"] not in seen:
            seen.add(a["path"])
            unique.append(a)

    # Sort: videos first, then gifs, then images
    type_order = {"video": 0, "gif": 1, "diagram": 2, "image": 3}
    unique.sort(key=lambda a: (type_order.get(a["type"], 9), a["path"]))

    lines = [f"Found {len(unique)} media assets:"]
    for a in unique:
        lines.append(f"  [{a['type']:7s}] {a['path']} ({a['size']})")

    return "\n".join(lines)


def scan_local_workspace(local_path: str) -> Dict[str, str]:
    """
    Synchronous function that collects workspace context from the filesystem.

    Returns a dict with keys:
      file_tree, git_branch, git_status, git_recent_log, git_diff,
      git_unpushed, key_files, recently_changed
    """
    context: Dict[str, str] = {}

    if not os.path.isdir(local_path):
        logger.warning("Workspace path does not exist or is not a directory: %s", local_path)
        return context

    # Directory tree (2 levels)
    context["file_tree"] = _build_file_tree(local_path, max_depth=2)

    # Git information — gracefully handles non-git directories
    context["git_branch"] = _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=local_path
    )
    context["git_status"] = _run(
        ["git", "status", "--short"], cwd=local_path
    )
    # Last 20 commits
    context["git_recent_log"] = _run(
        ["git", "log", "--oneline", "-20"], cwd=local_path
    )
    # Uncommitted changes (diff vs HEAD, truncated)
    diff = _run(
        ["git", "diff", "HEAD", "--stat"], cwd=local_path
    )
    if len(diff) > 3000:
        diff = diff[:3000] + "\n... (truncated)"
    context["git_diff"] = diff

    # Commits not yet pushed to remote
    context["git_unpushed"] = _run(
        ["git", "log", "@{u}..", "--oneline"], cwd=local_path
    )

    # Key config/doc files
    context["key_files"] = _read_key_files(local_path)

    # Recently changed files
    context["recently_changed"] = _recent_changed_files(local_path)

    # Media assets (images, videos, GIFs, diagrams)
    context["media_assets"] = _discover_media_assets(local_path)

    return context


async def perform_scan(
    project_id: uuid.UUID,
    local_path: str,
    db: AsyncSession,
) -> WorkspaceSnapshot:
    """
    Run a full workspace scan, summarise with the local AI model, and persist
    the result as a WorkspaceSnapshot.

    The scan itself is CPU/IO-bound (subprocess calls), so it runs in the
    default executor to avoid blocking the event loop.
    """
    loop = asyncio.get_event_loop()
    raw_data: Dict[str, str] = await loop.run_in_executor(
        None, scan_local_workspace, local_path
    )

    # Build a compact text representation for summarisation
    summary_input_parts: List[str] = []
    if raw_data.get("file_tree"):
        summary_input_parts.append(f"## Directory Tree\n{raw_data['file_tree']}")
    if raw_data.get("git_branch"):
        summary_input_parts.append(f"## Git Branch\n{raw_data['git_branch']}")
    if raw_data.get("git_status"):
        summary_input_parts.append(f"## Git Status\n{raw_data['git_status']}")
    if raw_data.get("git_recent_log"):
        summary_input_parts.append(f"## Recent Commits\n{raw_data['git_recent_log']}")
    if raw_data.get("git_unpushed"):
        summary_input_parts.append(f"## Unpushed Commits\n{raw_data['git_unpushed']}")
    if raw_data.get("key_files"):
        summary_input_parts.append(f"## Key Files\n{raw_data['key_files']}")
    if raw_data.get("media_assets"):
        summary_input_parts.append(f"## Available Media Assets\n{raw_data['media_assets']}")
    summary_input = "\n\n".join(summary_input_parts)

    # Summarise with the LOCAL model — workspace code never reaches cloud AI
    summary = ""
    try:
        local_ai = get_local_client()
        summary = await local_ai.complete(
            system=(
                "You are a senior developer analyzing a local project workspace. "
                "Produce a concise (3-5 paragraph) briefing covering:\n"
                "1. Project structure and main components\n"
                "2. Current git state (branch, uncommitted changes, unpushed work)\n"
                "3. Recent development activity (commit messages)\n"
                "4. Tech stack inferred from config files\n"
                "5. Any notable or in-progress work\n"
                "6. Available media assets (images, videos, GIFs, diagrams) that could "
                "be used in social media posts or documentation — note their paths and "
                "what they likely depict based on filenames and location\n\n"
                "Be specific. Cite actual file names and commit messages. "
                "Do NOT include API keys, tokens, passwords, or credentials."
            ),
            user=f"Workspace data:\n\n{summary_input[:8000]}",
        )
    except Exception:
        logger.exception(
            "Local AI summarisation failed for workspace %s; storing raw data only",
            local_path,
        )
        # Fallback: compose a minimal summary from available data
        parts: List[str] = []
        if raw_data.get("git_branch"):
            parts.append(f"Branch: {raw_data['git_branch']}")
        if raw_data.get("git_status"):
            parts.append(f"Git status:\n{raw_data['git_status']}")
        if raw_data.get("git_recent_log"):
            parts.append(f"Recent commits:\n{raw_data['git_recent_log']}")
        summary = "\n".join(parts) if parts else "Workspace scan completed. AI summary unavailable."

    snapshot = WorkspaceSnapshot(
        project_id=project_id,
        local_path=local_path,
        summary=summary,
        raw_data=raw_data,
        git_branch=raw_data.get("git_branch") or None,
        git_status=raw_data.get("git_status") or None,
        git_recent_log=raw_data.get("git_recent_log") or None,
    )
    db.add(snapshot)
    await db.flush()
    await db.refresh(snapshot)
    return snapshot


async def get_latest_snapshot(
    project_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[WorkspaceSnapshot]:
    """Return the most recent WorkspaceSnapshot for a project, or None."""
    result = await db.execute(
        select(WorkspaceSnapshot)
        .where(WorkspaceSnapshot.project_id == project_id)
        .order_by(WorkspaceSnapshot.scanned_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
