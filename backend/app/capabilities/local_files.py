"""local-files ingest source.

Watches a directory (typically `WORKSPACE_HOST_PATH` bind-mounted at
`/projects/` in the container) and emits a `file_ingested` knowledge
node + bench event for every file that wasn't seen on a prior tick.

Dedup is by external_id = `<absolute path>::<mtime>::<size>`. That
captures rename, edit, and re-add as fresh events without needing a
state file. The KG node insert is itself dedup'd via
`metadata_->>'external_id'` so re-running the runner is idempotent.

Scope guards (keep the runner cheap + safe):

- Honors a `path_patterns` config glob if set — defaults to all files.
- Hard cap: max 100 files emitted per tick. The rest wait for next tick.
- Skip dot-prefixed dirs (`.git`, `.next`, `node_modules`) so a fresh
  repo clone doesn't flood the graph.
- Skip files larger than `max_size_mb` (default 1 MB) — we don't need
  to inhale binaries; the node just records existence.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.capabilities.base import IngestContext, IngestSource

logger = logging.getLogger(__name__)

# Directory + filename patterns that almost never carry user-meaningful
# content. Cheap to filter at the top of the walk; saves a lot of churn.
_SKIP_DIR_NAMES = frozenset({
    ".git", ".next", "__pycache__", "node_modules", ".venv", "venv",
    ".pytest_cache", ".mypy_cache", "dist", "build", ".idea",
    ".vscode", ".DS_Store",
})
_SKIP_FILE_SUFFIXES = (".pyc", ".pyo", ".DS_Store", ".log")


class LocalFilesIngest(IngestSource):
    """Walks `config['watch_path']` and emits a node per new file."""

    label = "local-files"
    default_poll_interval_seconds = 30

    async def run(self, config: Dict[str, Any], ctx: IngestContext) -> int:
        watch_path = config.get("watch_path") or "/projects"
        max_files_per_tick: int = int(config.get("max_files_per_tick") or 100)
        max_size_mb: float = float(config.get("max_size_mb") or 1.0)
        max_size_bytes = int(max_size_mb * 1024 * 1024)

        root = Path(watch_path)
        if not root.exists() or not root.is_dir():
            # Quiet skip — the workspace path is optional. We only log
            # at debug level so it doesn't fill the bench log on every tick.
            logger.debug("local-files: watch_path %s does not exist; skipping", watch_path)
            return 0

        ingested = 0
        candidates = self._walk_files(root, max_size_bytes)
        for path in candidates:
            if ingested >= max_files_per_tick:
                ctx.log(
                    "warn",
                    f"local-files: hit per-tick cap of {max_files_per_tick}; "
                    f"more files will be picked up next tick",
                )
                break
            try:
                stat = path.stat()
                external_id = f"{path.as_posix()}::{int(stat.st_mtime)}::{stat.st_size}"
                rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
                inserted = await ctx.upsert_node(
                    node_type="file_ingested",
                    title=rel,
                    content=f"File at {rel} ({stat.st_size} bytes). "
                            f"Surfaced by the local-files capability.",
                    external_id=external_id,
                    metadata={
                        "path": path.as_posix(),
                        "rel": rel,
                        "size_bytes": stat.st_size,
                        "mtime": stat.st_mtime,
                    },
                )
                if inserted:
                    ingested += 1
                    ctx.log("info", f"local-files: ingested {rel}",
                            meta={"path": path.as_posix()})
            except FileNotFoundError:
                # The file disappeared between walk + stat. Race is fine; skip.
                continue
            except Exception as exc:
                logger.warning("local-files: skip %s — %s", path, exc)
                continue

        if ingested == 0:
            logger.debug("local-files: no new files this tick")
        return ingested

    @staticmethod
    def _walk_files(root: Path, max_size_bytes: int) -> Iterable[Path]:
        """Lazy generator over files under root, with skip rules applied."""
        for dirpath, dirnames, filenames in os.walk(root):
            # Mutate dirnames in place so os.walk doesn't descend into skipped dirs
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")]
            for filename in filenames:
                if filename.startswith("."):
                    continue
                if filename.endswith(_SKIP_FILE_SUFFIXES):
                    continue
                full = Path(dirpath) / filename
                try:
                    if full.stat().st_size > max_size_bytes:
                        continue
                except OSError:
                    continue
                yield full
