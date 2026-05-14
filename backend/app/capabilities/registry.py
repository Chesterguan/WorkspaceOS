"""Capability runner registry — name → class.

Authors who add a new capability runner edit this file in their PR.
This is intentional: capabilities are trusted code, not arbitrary
file-drop plugins. The registry is the audit surface.
"""
from typing import Dict, Type

from app.capabilities.base import IngestSource
from app.capabilities.local_files import LocalFilesIngest


# Map of `name` (as written in extension manifest's `capabilities`) → runner class
INGEST_SOURCES: Dict[str, Type[IngestSource]] = {
    "local_files": LocalFilesIngest,
}


def get_ingest_source(name: str) -> Type[IngestSource]:
    """Look up a runner by name. Raises KeyError if unregistered."""
    return INGEST_SOURCES[name]


def list_ingest_sources() -> list[str]:
    """All registered runner names — useful for diagnostics endpoints."""
    return sorted(INGEST_SOURCES.keys())
