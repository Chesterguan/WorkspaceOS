"""Reserved privacy:* tag namespace and policy resolution.

The tag namespace lives on MemoryEntry.metadata_["tags"] (a list of
strings, populated by file ingest + manual tagging). Reserved values:

    privacy:local-only      — never reaches cloud; replaced by stub
    privacy:redact-content  — title + headers preserved; body redacted
    privacy:redact-values   — schema preserved; cells become placeholders
    privacy:public          — explicit override of any project default

Project.privacy_default ∈ {'open', 'strict'} applies when no explicit
privacy:* tag is present. 'strict' treats untagged entries as
redact-content; 'open' lets them through.

See docs/privacy/measurement-and-redaction.md.
"""
from __future__ import annotations

import enum
from typing import List, Optional


LOCAL_ONLY = "privacy:local-only"
REDACT_CONTENT = "privacy:redact-content"
REDACT_VALUES = "privacy:redact-values"
PUBLIC = "privacy:public"

_RESERVED = {LOCAL_ONLY, REDACT_CONTENT, REDACT_VALUES, PUBLIC}
# Public alias for use by router-layer code that shouldn't reach for the underscore name.
RESERVED_TAGS = _RESERVED


class PrivacyPolicy(enum.Enum):
    LOCAL_ONLY = "local_only"
    REDACT_CONTENT = "redact_content"
    REDACT_VALUES = "redact_values"
    PUBLIC = "public"


_TAG_TO_POLICY = {
    LOCAL_ONLY: PrivacyPolicy.LOCAL_ONLY,
    REDACT_CONTENT: PrivacyPolicy.REDACT_CONTENT,
    REDACT_VALUES: PrivacyPolicy.REDACT_VALUES,
    PUBLIC: PrivacyPolicy.PUBLIC,
}


def resolve_policy(
    entry_tags: Optional[List[str]],
    project_default: str = "open",
) -> PrivacyPolicy:
    """Pick the effective policy for an entry.

    Explicit privacy:* tag wins. Otherwise: strict default → REDACT_CONTENT,
    open default → PUBLIC.
    """
    tags = entry_tags or []
    for tag in tags:
        if tag in _TAG_TO_POLICY:
            return _TAG_TO_POLICY[tag]
    if project_default == "strict":
        return PrivacyPolicy.REDACT_CONTENT
    return PrivacyPolicy.PUBLIC


def is_reserved(tag: str) -> bool:
    return tag in _RESERVED
