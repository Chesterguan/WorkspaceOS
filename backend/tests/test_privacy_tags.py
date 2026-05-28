"""Reserved privacy:* tag namespace + resolution helpers."""
from __future__ import annotations

import pytest

from app.services.privacy_tags import (
    LOCAL_ONLY, REDACT_CONTENT, REDACT_VALUES, PUBLIC,
    resolve_policy, PrivacyPolicy,
)


def test_explicit_tag_wins_over_project_default():
    policy = resolve_policy(
        entry_tags=["privacy:local-only", "topic:auth"],
        project_default="open",
    )
    assert policy is PrivacyPolicy.LOCAL_ONLY


def test_project_strict_default_applies_when_no_explicit_tag():
    policy = resolve_policy(
        entry_tags=["topic:auth"],
        project_default="strict",
    )
    assert policy is PrivacyPolicy.REDACT_CONTENT


def test_project_open_default_means_public():
    policy = resolve_policy(entry_tags=[], project_default="open")
    assert policy is PrivacyPolicy.PUBLIC


def test_public_tag_overrides_strict_default():
    policy = resolve_policy(
        entry_tags=["privacy:public"],
        project_default="strict",
    )
    assert policy is PrivacyPolicy.PUBLIC
