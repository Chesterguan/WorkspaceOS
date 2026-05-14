"""Slash command handlers.

A slash command is a palette entry the user picks (or types) to trigger
an action. Two handler kinds are supported in the manifest config:

  handler_kind: api_call  → frontend POSTs to handler_target with the
                            current bench context (project_id, etc.) as
                            JSON; the body of the response can carry a
                            toast message or follow-up navigation.
  handler_kind: navigate  → frontend uses next/router to push the
                            handler_target path.

Either way, the heavy lifting happens in already-registered backend
endpoints — slash_command capabilities do NOT execute arbitrary code
themselves. This keeps the trust surface narrow: extension authors
declare WHICH endpoint to call; the endpoint itself is core code.

Concrete handlers used by the example capabilities live here as small
async functions registered in SLASH_RUNNERS. Frontend invokes them via
`POST /capabilities/runners/<name>/trigger`.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.event_stream import emit

logger = logging.getLogger(__name__)


SlashHandler = Callable[[Dict[str, Any], AsyncSession, uuid.UUID], Awaitable[Dict[str, Any]]]


async def _trigger_local_files_scan(
    payload: Dict[str, Any],
    db: AsyncSession,
    user_id: uuid.UUID,
) -> Dict[str, Any]:
    """Run the local_files ingest source once, off-schedule.

    The runner is normally polled every 30s by ingest_runner. This hook
    lets the user force an immediate tick from the palette — handy if
    they just dropped a file and don't want to wait.
    """
    from app.capabilities.base import IngestContext
    from app.capabilities.local_files import LocalFilesIngest

    runner = LocalFilesIngest()
    ctx = IngestContext(user_id=user_id, source="local-files-watcher:local_files")
    count = await runner.run({"watch_path": "/projects"}, ctx)
    emit("info", "slash-command", f"local-files scan ran on demand — {count} new files")
    return {"ok": True, "ingested": count, "toast": f"Scanned — {count} new files."}


# ── Adaptive registry (v0.2.1, v0.3 path reserved) ──────────────────
# Single source of truth — mutated by register_slash_runner() at import
# time. v0.3 path: discover_entry_points() will scan installed
# packages under `workspaceos.slash_runners`. See
# `app/capabilities/registry.py` for the canonical adaptive pattern.

SLASH_RUNNERS: Dict[str, SlashHandler] = {}


def register_slash_runner(name: str, handler: SlashHandler) -> None:
    existing = SLASH_RUNNERS.get(name)
    if existing is handler:
        return
    if existing is not None:
        raise ValueError(
            f"slash_runner name conflict: {name!r} already registered; "
            f"refusing to overwrite."
        )
    SLASH_RUNNERS[name] = handler
    logger.debug("registered slash_runner: %s", name)


def discover_entry_points() -> None:
    """v0.3 hook — scan installed packages under
    `workspaceos.slash_runners` entry-point group. No-op for now."""
    return None  # ← Phase 3: replace with importlib.metadata scan


def list_runners() -> list[str]:
    return sorted(SLASH_RUNNERS.keys())


# In-tree defaults
register_slash_runner("trigger_local_files_scan", _trigger_local_files_scan)

# v0.3 activation: uncomment the next line.
# discover_entry_points()
