"""Tag-resolving prompt assembler — turns memory entries into stubs."""
from __future__ import annotations

import uuid

import pytest

from app.models.memory import MemoryEntry
from app.services.privacy_tags import LOCAL_ONLY, REDACT_CONTENT
from app.services.privacy_assembler import assemble_context


def _entry(content: str, tags=None, entry_type="narrative_fact", filename=None) -> MemoryEntry:
    md = {"tags": list(tags or [])}
    if filename:
        md["filename"] = filename
    return MemoryEntry(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        entry_type=entry_type,
        content=content,
        metadata_=md,
    )


def test_local_only_entry_is_replaced_with_stub():
    e = _entry("87.3% accuracy on private corpus", tags=[LOCAL_ONLY], filename="results.csv")
    out, summary = assemble_context([e], project_default="open")

    assert "87.3%" not in out
    assert "not sent to cloud" in out
    assert "results.csv" in out
    assert summary.entries_stubbed == 1


def test_redact_content_entry_keeps_type_and_filename_drops_body():
    e = _entry("secret body text", tags=[REDACT_CONTENT], filename="methods.md")
    out, summary = assemble_context([e], project_default="open")

    assert "secret body text" not in out
    assert "methods.md" in out
    assert "body redacted" in out


def test_public_entry_is_emitted_verbatim():
    e = _entry("This is public note content.", tags=[])
    out, summary = assemble_context([e], project_default="open")

    assert "This is public note content." in out
    assert summary.entries_stubbed == 0


def test_strict_default_applies_to_untagged_entry():
    e = _entry("body content", tags=[])
    out, summary = assemble_context([e], project_default="strict")

    assert "body content" not in out
    assert "body redacted" in out


def test_no_tagged_bytes_leak_into_output():
    """For every LOCAL_ONLY / REDACT_CONTENT entry, no substring of the
    original content of length >= 8 may appear in the output."""
    sensitive = "verylongsecretvalue123456789"
    e = _entry(sensitive, tags=[LOCAL_ONLY])
    out, _ = assemble_context([e], project_default="open")
    for n in range(8, len(sensitive) + 1):
        for i in range(0, len(sensitive) - n + 1):
            chunk = sensitive[i:i + n]
            assert chunk not in out, f"sensitive chunk {chunk!r} leaked into output"
