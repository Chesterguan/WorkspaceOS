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


@pytest.mark.parametrize(
    "tags",
    [
        [PUBLIC, LOCAL_ONLY],  # AI-emitted public first, user local-only second
        [LOCAL_ONLY, PUBLIC],  # reverse order
    ],
)
def test_conflicting_tags_resolve_to_most_restrictive(tags):
    """M-1: with conflicting privacy:* tags, the most restrictive wins
    regardless of order. An AI-emitted privacy:public must never override a
    user's privacy:local-only just because of list position."""
    assert resolve_policy(tags, project_default="open") is PrivacyPolicy.LOCAL_ONLY


def test_restrictiveness_ordering_is_total():
    """redact-content beats redact-values beats public, order-independent."""
    assert resolve_policy([PUBLIC, REDACT_VALUES]) is PrivacyPolicy.REDACT_VALUES
    assert resolve_policy([REDACT_VALUES, REDACT_CONTENT]) is PrivacyPolicy.REDACT_CONTENT
    assert resolve_policy([PUBLIC, REDACT_CONTENT, REDACT_VALUES]) is PrivacyPolicy.REDACT_CONTENT
