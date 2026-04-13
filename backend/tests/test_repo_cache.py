"""
Unit tests for the repo_cache service.

subprocess.run is monkey-patched so no real git calls happen — the tests
verify argument construction, cache-directory layout, and stale-fallback
behaviour when a fetch fails.
"""
import base64
import os
import subprocess
import uuid
from types import SimpleNamespace
from typing import List, Optional

import pytest

from app.services import repo_cache


# ---------- helpers ----------------------------------------------------------

def _fake_project(slug: str = "myproj", repo: Optional[str] = "octocat/hello"):
    """Build a minimal stand-in for an ORM Project row."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        slug=slug,
        github_repo=repo,
        github_branch="main",
    )


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def tmp_cache_root(tmp_path, monkeypatch):
    """Point repo_cache at an isolated tmp dir and clear per-test locks."""
    monkeypatch.setattr(repo_cache, "CACHE_ROOT", str(tmp_path))
    repo_cache._locks.clear()
    yield tmp_path


# ---------- cold clone -------------------------------------------------------

async def test_cold_clone_creates_cache_dir(tmp_cache_root, monkeypatch):
    project = _fake_project()
    calls = []  # type: List[List[str]]

    def fake_run_git(args, cwd=None, extra_env=None, timeout=120):
        calls.append(list(args))
        # Simulate a successful clone by materialising the .git directory
        if "clone" in args:
            target = args[-1]
            os.makedirs(os.path.join(target, ".git"), exist_ok=True)
        return _completed(returncode=0)

    monkeypatch.setattr(repo_cache, "_run_git", fake_run_git)

    path = await repo_cache.get_or_clone_branch(project, "main", token="t0k")

    assert os.path.isdir(path)
    assert os.path.isdir(os.path.join(path, ".git"))
    # Path is scoped by user / slug / encoded branch
    expected_suffix = os.path.join(str(project.user_id), project.slug, "main")
    assert path.endswith(expected_suffix)
    # Exactly one git invocation (clone) on the cold path
    assert len(calls) == 1
    clone_args = calls[0]
    assert "clone" in clone_args
    assert "--depth" in clone_args
    assert "--single-branch" in clone_args
    assert "--branch" in clone_args
    # Branch target is passed as a positional after --branch
    assert clone_args[clone_args.index("--branch") + 1] == "main"
    # Auth header is HTTP Basic with x-access-token:<token> base64-encoded
    # (the GitHub Actions pattern — see _auth_args docstring for why).
    assert "-c" in clone_args
    expected_b64 = base64.b64encode(b"x-access-token:t0k").decode("ascii")
    assert any(
        f"http.extraheader=AUTHORIZATION: basic {expected_b64}" == a
        for a in clone_args
    )


async def test_cold_clone_without_token_omits_auth_header(tmp_cache_root, monkeypatch):
    project = _fake_project()
    calls = []  # type: List[List[str]]

    def fake_run_git(args, cwd=None, extra_env=None, timeout=120):
        calls.append(list(args))
        if "clone" in args:
            os.makedirs(os.path.join(args[-1], ".git"), exist_ok=True)
        return _completed(returncode=0)

    monkeypatch.setattr(repo_cache, "_run_git", fake_run_git)
    await repo_cache.get_or_clone_branch(project, "main", token=None)

    clone_args = calls[0]
    assert not any("extraheader" in a for a in clone_args)


async def test_cold_clone_failure_raises(tmp_cache_root, monkeypatch):
    project = _fake_project()

    def fake_run_git(args, cwd=None, extra_env=None, timeout=120):
        return _completed(returncode=128, stderr="repository not found")

    monkeypatch.setattr(repo_cache, "_run_git", fake_run_git)

    with pytest.raises(RuntimeError, match="repository not found"):
        await repo_cache.get_or_clone_branch(project, "main", token=None)


# ---------- warm fetch -------------------------------------------------------

async def test_warm_fetch_reuses_cache(tmp_cache_root, monkeypatch):
    project = _fake_project()
    cache_dir = repo_cache._cache_dir_for(project, "main")
    os.makedirs(os.path.join(cache_dir, ".git"))

    calls = []  # type: List[List[str]]

    def fake_run_git(args, cwd=None, extra_env=None, timeout=120):
        calls.append(list(args))
        return _completed(returncode=0)

    monkeypatch.setattr(repo_cache, "_run_git", fake_run_git)

    path = await repo_cache.get_or_clone_branch(project, "main", token="t0k")

    assert path == cache_dir
    # Warm path: fetch + reset, no clone
    assert any("fetch" in c for c in calls)
    assert any("reset" in c for c in calls)
    assert not any("clone" in c for c in calls)


async def test_fetch_failure_falls_back_to_stale_cache(tmp_cache_root, monkeypatch):
    project = _fake_project()
    cache_dir = repo_cache._cache_dir_for(project, "main")
    os.makedirs(os.path.join(cache_dir, ".git"))

    def fake_run_git(args, cwd=None, extra_env=None, timeout=120):
        if "fetch" in args:
            return _completed(returncode=1, stderr="fatal: unable to access")
        return _completed(returncode=0)

    monkeypatch.setattr(repo_cache, "_run_git", fake_run_git)

    # Must not raise — stale cache is usable
    path = await repo_cache.get_or_clone_branch(project, "main", token=None)
    assert path == cache_dir


# ---------- branch encoding --------------------------------------------------

async def test_branch_with_slash_is_encoded(tmp_cache_root, monkeypatch):
    project = _fake_project()

    def fake_run_git(args, cwd=None, extra_env=None, timeout=120):
        if "clone" in args:
            os.makedirs(os.path.join(args[-1], ".git"), exist_ok=True)
        return _completed(returncode=0)

    monkeypatch.setattr(repo_cache, "_run_git", fake_run_git)

    path = await repo_cache.get_or_clone_branch(project, "feature/foo", token=None)

    assert path.endswith("feature%2Ffoo")
    # Raw slash must not appear inside the per-branch segment
    branch_segment = path.split(project.slug + os.sep, 1)[1]
    assert "/" not in branch_segment


# ---------- cache cleanup ----------------------------------------------------

async def test_remove_repo_cache_deletes_all_branches(tmp_cache_root):
    project = _fake_project()
    dir_main = repo_cache._cache_dir_for(project, "main")
    dir_feat = repo_cache._cache_dir_for(project, "feature/x")
    os.makedirs(os.path.join(dir_main, ".git"))
    os.makedirs(os.path.join(dir_feat, ".git"))

    await repo_cache.remove_repo_cache(project)

    assert not os.path.exists(repo_cache._project_cache_dir(project))


async def test_remove_repo_cache_missing_is_noop(tmp_cache_root):
    project = _fake_project()
    # Should not raise even though nothing was ever cached
    await repo_cache.remove_repo_cache(project)


# ---------- validation -------------------------------------------------------

async def test_missing_github_repo_raises(tmp_cache_root):
    project = _fake_project(repo=None)
    with pytest.raises(ValueError, match="github_repo"):
        await repo_cache.get_or_clone_branch(project, "main", token=None)
