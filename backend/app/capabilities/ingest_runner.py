"""Boots ingest_source capabilities declared by loaded extensions.

On app startup, `start_all` enumerates `ext_service.get_all_extensions()`,
collects every `kind: ingest_source` capability, looks up its runner in
the registry, and launches one asyncio task per runner that polls on the
configured interval.

Each runner gets a single dedicated `asyncio.Task` for its lifetime.
Cancellation on shutdown is cooperative — the task awaits
`asyncio.sleep(interval)` between ticks and cancels cleanly when the
host's lifespan tears down.

Errors inside a tick are logged + swallowed; we do not let one bad
runner take down the others. A repeatedly-failing runner shows up in
the bench TUI log via `ctx.log("error", ...)` from the run() itself,
plus a per-runner backoff to prevent hot-looping.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.capabilities.base import IngestContext, IngestSource
from app.capabilities.registry import INGEST_SOURCES
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services import capability_settings_service, extensions as ext_service

logger = logging.getLogger(__name__)


# Runner tasks held at module scope so lifespan can cancel them on shutdown.
_tasks: List[asyncio.Task] = []


async def _resolve_default_user_id() -> Optional[uuid.UUID]:
    """Pick a user to attribute ingested nodes to.

    Phase 2 doesn't yet have a per-user capability config — the framework
    is single-tenant in practice. We pick the first registered user.
    Multi-tenant fan-out is a Phase 3 concern.
    """
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).order_by(User.created_at.asc()).limit(1))
        u = res.scalar_one_or_none()
        return u.id if u else None


async def _runner_loop(
    runner: IngestSource,
    manifest_config: Dict[str, Any],
    extension_id: str,
    capability_name: str,
    source_label: str,
    interval_seconds: int,
) -> None:
    """One runner's lifetime. Polls until cancelled.

    `manifest_config` is the static config from the extension's
    manifest. The DB overlay (set via Settings → Capabilities →
    Configure) is merged on top each tick — so saving new credentials
    in the UI takes effect on the next poll, no restart needed.
    """
    user_id = await _resolve_default_user_id()
    if user_id is None:
        logger.info(
            "capability %s: no users registered yet; will retry once a user exists",
            source_label,
        )
        # Wait until a user shows up; this is the fresh-install case.
        # Poll lazily so we don't hammer the DB.
        while user_id is None:
            await asyncio.sleep(30)
            user_id = await _resolve_default_user_id()

    ctx = IngestContext(user_id=user_id, source=source_label)
    consecutive_errors = 0
    while True:
        try:
            overlay = await capability_settings_service.get_overlay(
                extension_id, capability_name,
            )
            effective = capability_settings_service.effective_config(
                manifest_config, overlay,
            )
            count = await runner.run(effective, ctx)
            consecutive_errors = 0
            if count:
                logger.debug("capability %s: ingested %d items", source_label, count)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            consecutive_errors += 1
            logger.exception("capability %s: tick failed (%dx)", source_label, consecutive_errors)
            ctx.log("error", f"{source_label}: tick failed — {exc}", meta={"errors": consecutive_errors})
        # Backoff on sustained failure so we don't hot-loop. Caps at ~5 min.
        sleep_for = interval_seconds * min(1 + consecutive_errors, 10)
        await asyncio.sleep(sleep_for)


def start_all() -> None:
    """Discover + schedule every ingest_source capability."""
    extensions = ext_service.get_all_extensions()
    started = 0
    skipped: List[str] = []
    for ext in extensions:
        for cap in ext.manifest.capabilities:
            if cap.kind != "ingest_source":
                continue
            runner_cls = INGEST_SOURCES.get(cap.name)
            if runner_cls is None:
                skipped.append(f"{ext.manifest.id}/{cap.name}")
                logger.info(
                    "capability %s/%s declared but no runner registered — skipping",
                    ext.manifest.id, cap.name,
                )
                continue
            runner = runner_cls()
            config = cap.config or {}
            interval = int(
                config.get("poll_interval_seconds")
                or runner.default_poll_interval_seconds
            )
            source_label = f"{ext.manifest.id}:{cap.name}"
            task = asyncio.create_task(
                _runner_loop(
                    runner,
                    config,
                    ext.manifest.id,
                    cap.name,
                    source_label,
                    interval,
                ),
                name=f"ingest_runner:{source_label}",
            )
            _tasks.append(task)
            started += 1
            logger.info(
                "capability scheduled: %s every %ds", source_label, interval,
            )
    if started == 0 and not skipped:
        logger.info("capabilities: no ingest_source extensions found")


async def stop_all() -> None:
    """Cancel every runner task. Awaits clean termination."""
    for task in _tasks:
        task.cancel()
    for task in _tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("capability runner shutdown raised")
    _tasks.clear()
