"""
Repo cache service — GitHub Desktop-style persistent clones for remote-only
projects.

When a project references a GitHub repo but has no usable `local_path` on
disk (e.g. it was imported from the repo picker rather than a locally-mounted
workspace), any feature that reads the working tree — workspace scan, file
ingest, worklog — will fail. This module fills that gap by keeping a
persistent shallow clone of each scanned branch under the backend's writable
data volume. Subsequent scans fast-forward the existing clone instead of
re-cloning, and a failed fetch falls back to the cached state (stale but
usable) rather than erroring out.

Disk layout (scoped by user_id to respect multi-tenant isolation, keyed by
project slug so a repo rename on GitHub doesn't invalidate the cache):

    /app/data/repo-cache/<user_id>/<project_slug>/<urlencoded_branch>/

Authentication uses the one-shot `http.extraheader` pattern so the token is
never written to .git/config:

    git -c http.extraheader="AUTHORIZATION: bearer <token>" clone|fetch ...

Concurrency is serialised per (project_id, branch) via an in-process
asyncio.Lock dict. Two scans targeting different branches of the same repo
therefore run in parallel; two scans targeting the same branch serialise.
"""
import asyncio
import base64
import logging
import os
import shutil
import subprocess
import uuid
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Root of the on-disk cache. Overridable in tests via monkeypatch.
CACHE_ROOT = "/app/data/repo-cache"

# Shallow-clone depth — enough for workspace_scanner's `git log -20` and
# `git diff HEAD~10 HEAD` queries; unshallow on demand if ever needed.
CLONE_DEPTH = 50

# Subprocess timeout (seconds) for any individual git command.
GIT_TIMEOUT = 180

# asyncio.Lock per (project_id, branch). Lazily populated; cleared in tests.
_locks: Dict[Tuple[str, str], asyncio.Lock] = {}


# ---------- path helpers -----------------------------------------------------

def _encode_branch(branch: str) -> str:
    """Percent-encode a branch name for use as a single filesystem segment."""
    return quote(branch, safe="")


def _project_cache_dir(project) -> str:
    """Directory holding every cached branch checkout for one project."""
    return os.path.join(CACHE_ROOT, str(project.user_id), project.slug)


def _cache_dir_for(project, branch: str) -> str:
    """Directory holding the working tree for a single (project, branch)."""
    return os.path.join(_project_cache_dir(project), _encode_branch(branch))


def _is_valid_clone(path: str) -> bool:
    """A directory counts as a valid clone if it contains a `.git` subdir."""
    return os.path.isdir(os.path.join(path, ".git"))


def _build_clone_url(github_repo: str) -> str:
    """Turn `owner/name` into the HTTPS clone URL (no embedded credentials)."""
    return f"https://github.com/{github_repo}.git"


def _auth_args(token: Optional[str]) -> List[str]:
    """
    Build the `-c http.extraheader=...` prefix that authenticates one git
    invocation without persisting the token to .git/config.

    Uses HTTP Basic auth with `x-access-token:<token>` base64-encoded — this
    is the exact pattern GitHub Actions' `actions/checkout` uses, and it's
    the only form GitHub's git-http endpoint actually honours for PATs.
    The naive `bearer <token>` form is silently rejected (the server
    responds 401 and git falls through to an interactive username prompt,
    which then hangs or errors out).

    Returns [] when no token is supplied — public clones still work fine.
    """
    if not token:
        return []
    encoded = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    return ["-c", f"http.extraheader=AUTHORIZATION: basic {encoded}"]


def _lock_for(project_id, branch: str) -> asyncio.Lock:
    """Return (and lazily create) the asyncio.Lock for a (project, branch) pair."""
    key = (str(project_id), branch)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


# ---------- subprocess wrapper ----------------------------------------------

def _run_git(
    args: List[str],
    cwd: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
    timeout: int = GIT_TIMEOUT,
) -> subprocess.CompletedProcess:
    """
    Run `git <args...>` and return the CompletedProcess. Never raises on a
    non-zero exit — callers inspect `.returncode` so they can distinguish
    "fetch failed, fall back to stale cache" from "clone failed, give up".

    GIT_TERMINAL_PROMPT=0 and GIT_ASKPASS=/bin/true force git to fail fast
    instead of blocking on an interactive credential prompt if auth is
    misconfigured — critical when running inside a non-tty container.
    """
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_ASKPASS", "/bin/true")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


# ---------- public API -------------------------------------------------------

async def get_or_clone_branch(
    project,
    branch: str,
    token: Optional[str],
) -> str:
    """
    Ensure a shallow clone of (project, branch) exists in the cache and return
    its local path.

      * Cold miss: runs `git clone --depth N --single-branch --branch <b>`.
      * Warm hit:  runs `git fetch --depth N origin <b>` followed by
                   `git reset --hard origin/<b>`.
      * Fetch failure on the warm path: logs and returns the stale cache —
        the last-known good checkout is still usable for scanning.

    Raises ValueError if the project has no `github_repo`, and RuntimeError
    if a cold clone fails (there's nothing to fall back to in that case).
    """
    if not project.github_repo:
        raise ValueError(
            f"Project {project.slug} has no github_repo; cannot clone"
        )

    cache_dir = _cache_dir_for(project, branch)
    loop = asyncio.get_event_loop()

    async with _lock_for(project.id, branch):
        if _is_valid_clone(cache_dir):
            # ---- warm path: fetch + reset, fall back to stale on failure ---
            fetch_result = await loop.run_in_executor(
                None,
                lambda: _run_git(
                    [*_auth_args(token), "fetch", "--depth", str(CLONE_DEPTH),
                     "origin", branch],
                    cwd=cache_dir,
                ),
            )
            if fetch_result.returncode != 0:
                logger.warning(
                    "git fetch failed for %s@%s (rc=%d); using stale cache. "
                    "stderr=%s",
                    project.slug, branch, fetch_result.returncode,
                    (fetch_result.stderr or "").strip()[:500],
                )
                return cache_dir

            reset_result = await loop.run_in_executor(
                None,
                lambda: _run_git(
                    ["reset", "--hard", f"origin/{branch}"],
                    cwd=cache_dir,
                ),
            )
            if reset_result.returncode != 0:
                logger.warning(
                    "git reset --hard origin/%s failed for %s; returning "
                    "stale HEAD. stderr=%s",
                    branch, project.slug,
                    (reset_result.stderr or "").strip()[:500],
                )
            return cache_dir

        # ---- cold path: clone ---------------------------------------------
        os.makedirs(os.path.dirname(cache_dir), exist_ok=True)
        # Remove any stray non-.git junk at the target so clone has a clean slate
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)

        clone_url = _build_clone_url(project.github_repo)
        clone_result = await loop.run_in_executor(
            None,
            lambda: _run_git(
                [
                    *_auth_args(token),
                    "clone",
                    "--depth", str(CLONE_DEPTH),
                    "--single-branch",
                    "--branch", branch,
                    clone_url,
                    cache_dir,
                ],
                timeout=GIT_TIMEOUT,
            ),
        )
        if clone_result.returncode != 0:
            stderr = (clone_result.stderr or "").strip()[:500] or "unknown error"
            # Clean up a half-written directory so the next attempt is cold again
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir, ignore_errors=True)
            raise RuntimeError(
                f"git clone failed for {project.github_repo}@{branch}: {stderr}"
            )
        return cache_dir


async def remove_repo_cache(project) -> None:
    """
    Delete every cached branch for a project. Called from delete_project.
    Best-effort — logs and swallows filesystem errors so a flaky unlink
    doesn't block the DB delete.
    """
    path = _project_cache_dir(project)
    if not os.path.isdir(path):
        return
    try:
        shutil.rmtree(path)
    except Exception as exc:
        logger.warning("Failed to remove repo cache %s: %s", path, exc)


async def remove_branch(project, branch: str) -> None:
    """Delete one cached branch checkout. Best-effort."""
    path = _cache_dir_for(project, branch)
    if not os.path.isdir(path):
        return
    try:
        shutil.rmtree(path)
    except Exception as exc:
        logger.warning("Failed to remove branch cache %s: %s", path, exc)
