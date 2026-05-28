"""Tag-resolving prompt assembler.

Given a list of MemoryEntry + the project's privacy_default, return:
  - one assembled context string with privacy stubs for tagged entries
  - a RedactionSummary recording what was replaced

Callers wrap their cloud-prompt construction with assemble_context()
and feed the result into get_cloud_client().complete(). Tagged content
never reaches the cloud.

See docs/privacy/measurement-and-redaction.md#part-2a-tag-based-file-entry-redaction-primary.
"""
from __future__ import annotations

from typing import List, Tuple

from app.models.memory import MemoryEntry
from app.services.egress_recorder import RedactionSummary
from app.services.privacy_tags import PrivacyPolicy, resolve_policy


def _filename_of(entry: MemoryEntry) -> str:
    md = entry.metadata_ or {}
    return md.get("filename") or entry.entry_type


def _structural_hint(entry: MemoryEntry) -> str:
    """One-line shape hint for a stub: row × col counts, page counts, etc."""
    md = entry.metadata_ or {}
    if "shape" in md:
        return md["shape"]
    if entry.entry_type == "file":
        size_bytes = md.get("size_bytes")
        if size_bytes:
            return f"{size_bytes} bytes"
    return ""


def _stub_local_only(entry: MemoryEntry) -> str:
    fn = _filename_of(entry)
    hint = _structural_hint(entry)
    hint_part = f" — {hint}" if hint else ""
    return f"[private — {entry.entry_type} — {fn}{hint_part} — not sent to cloud]"


def _stub_redact_content(entry: MemoryEntry) -> str:
    fn = _filename_of(entry)
    # No content is included in the stub — only the entry type and filename
    # are preserved. Even the first line is omitted because for short entries
    # (single-line secrets, one-liner facts) the "title hint" would be the
    # full secret. The stub format is intentionally minimal.
    return f"[partial — {entry.entry_type} — {fn} — body redacted]"


def assemble_context(
    entries: List[MemoryEntry],
    project_default: str = "open",
) -> Tuple[str, RedactionSummary]:
    """Assemble a privacy-aware context string from the given entries.

    Returns:
      (context_string, redaction_summary)
    """
    parts: List[str] = []
    summary = RedactionSummary()

    for entry in entries:
        tags = (entry.metadata_ or {}).get("tags") or []
        policy = resolve_policy(tags, project_default=project_default)

        if policy is PrivacyPolicy.LOCAL_ONLY:
            parts.append(_stub_local_only(entry))
            summary.entries_stubbed += 1
            summary.bytes_replaced += len((entry.content or "").encode("utf-8"))
        elif policy is PrivacyPolicy.REDACT_CONTENT:
            parts.append(_stub_redact_content(entry))
            summary.entries_stubbed += 1
            summary.bytes_replaced += len((entry.content or "").encode("utf-8"))
        elif policy is PrivacyPolicy.REDACT_VALUES:
            # v1: treat as redact-content. True table-cell redaction is a
            # later refinement once we have parsed tabular data in memory.
            parts.append(_stub_redact_content(entry))
            summary.entries_stubbed += 1
            summary.bytes_replaced += len((entry.content or "").encode("utf-8"))
        else:  # PUBLIC
            parts.append(entry.content or "")

    return "\n\n".join(parts), summary
