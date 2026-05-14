"""Capability runner registry — adaptive (v0.2.1 + v0.3 path reserved).

Today (v0.2.1): runners are registered via `register_ingest_source()`
called at import time from the framework's own modules. The hardcoded
in-tree default list lives here as the single edit point for core
contributions.

v0.3 path (reserved, not active): `discover_entry_points()` will scan
Python packages installed in the environment for entries declared under
`workspaceos.ingest_sources` in their `pyproject.toml`. Third-party
authors will `pip install workspaceos-gmail-ingest` and the runner
auto-registers — no PR into core required.

The activation of v0.3 is a one-line change at the bottom of this
module (uncomment the `discover_entry_points()` call). Everything
else stays.

Same shape repeats for slash runners (slash.py) and action handlers
(actions.py) — see their registry sections.
"""
from __future__ import annotations

import logging
from typing import Dict, Type

from app.capabilities.base import IngestSource

logger = logging.getLogger(__name__)


# Single source of truth — mutated by register_ingest_source() at import
# time. Frontend / loader read from here.
INGEST_SOURCES: Dict[str, Type[IngestSource]] = {}


def register_ingest_source(name: str, cls: Type[IngestSource]) -> None:
    """Register a runner class under `name`. Idempotent — re-registering
    the same (name, cls) pair is a no-op; conflicting names raise so
    typos / double-imports surface at startup, not runtime."""
    existing = INGEST_SOURCES.get(name)
    if existing is cls:
        return
    if existing is not None:
        raise ValueError(
            f"ingest_source name conflict: {name!r} already registered as "
            f"{existing.__module__}.{existing.__name__}; refusing to overwrite "
            f"with {cls.__module__}.{cls.__name__}"
        )
    INGEST_SOURCES[name] = cls
    logger.debug("registered ingest_source: %s → %s", name, cls.__name__)


def discover_entry_points() -> None:
    """v0.3 hook — scan installed Python packages for capability runners.

    Reserved for v0.3. The implementation will use
    `importlib.metadata.entry_points(group='workspaceos.ingest_sources')`
    and call `register_ingest_source(ep.name, ep.load())` for each.
    Authors will declare in their pyproject.toml:

        [project.entry-points."workspaceos.ingest_sources"]
        gmail = "workspaceos_gmail_ingest:GmailIngest"

    Currently a no-op so v0.2.x boots without changes when no packages
    are installed. Flip the implementation in v0.3.
    """
    return None  # ← Phase 3: replace with entry-points scan


def get_ingest_source(name: str) -> Type[IngestSource]:
    """Look up a runner by name. Raises KeyError if unregistered."""
    return INGEST_SOURCES[name]


def list_ingest_sources() -> list[str]:
    """All registered runner names — useful for diagnostics endpoints."""
    return sorted(INGEST_SOURCES.keys())


# ── In-tree default runners ──────────────────────────────────────────
# Import the runner modules and register them. Adding a new in-tree
# runner is a 2-line change here.

from app.capabilities.local_files import LocalFilesIngest  # noqa: E402
from app.capabilities.benchling_import import BenchlingImport  # noqa: E402
from app.capabilities.zotero_sync import ZoteroSync  # noqa: E402
from app.capabilities.preprint_ingest import PreprintIngest  # noqa: E402
from app.capabilities.github_user_tools import GitHubUserTools  # noqa: E402
from app.capabilities.ot2_protocols import OT2ProtocolsIngest  # noqa: E402

register_ingest_source("local_files", LocalFilesIngest)
register_ingest_source("benchling_import", BenchlingImport)
register_ingest_source("zotero_sync", ZoteroSync)
register_ingest_source("preprint_ingest", PreprintIngest)
register_ingest_source("github_user_tools", GitHubUserTools)
register_ingest_source("ot2_protocols", OT2ProtocolsIngest)

# v0.3 activation: uncomment the next line.
# discover_entry_points()
