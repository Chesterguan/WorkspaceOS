"""Regression tests for the privacy leaks documented in
docs/privacy/known-leaks.md. Each test pins the contract: after the
fix, these calls must hit the local AI client, not the cloud one."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services import knowledge_service


@pytest.mark.asyncio
async def test_query_embedding_uses_local_client():
    """L-1: knowledge query embedding must go local, not cloud."""
    fake_local = AsyncMock()
    fake_local.embed.return_value = [0.0] * 768
    fake_cloud = AsyncMock()
    fake_cloud.embed.return_value = [9.9] * 768  # must NOT be called

    with patch.object(knowledge_service, "get_local_client", return_value=fake_local), \
         patch.object(knowledge_service, "get_cloud_client", return_value=fake_cloud):
        result = await knowledge_service.query_embedding("private research query")

    fake_local.embed.assert_awaited_once_with("private research query")
    fake_cloud.embed.assert_not_awaited()
    assert result == [0.0] * 768


@pytest.mark.asyncio
async def test_knowledge_extractor_embed_uses_local_client():
    """L-1 (extension): knowledge_extractor._embed must also go local."""
    from app.services import knowledge_extractor

    fake_local = AsyncMock()
    fake_local.embed.return_value = [0.0] * 768
    fake_cloud = AsyncMock()
    fake_cloud.embed.return_value = [9.9] * 768

    with patch.object(knowledge_extractor, "get_local_client", return_value=fake_local), \
         patch.object(knowledge_extractor, "get_cloud_client", return_value=fake_cloud):
        result = await knowledge_extractor._embed("decision: ship the prototype")

    fake_local.embed.assert_awaited_once_with("decision: ship the prototype")
    fake_cloud.embed.assert_not_awaited()
    assert result == [0.0] * 768


import uuid
import importlib
import inspect
from pathlib import Path


def test_no_direct_openai_client_instantiation_outside_ai_client():
    """L-2: only ai_client.py may instantiate OpenAIClient directly.

    Any other call site bypasses the CLOUD_AI_PROVIDER router and
    sends data to OpenAI even when the user picked a different
    provider. The allowed exceptions are gated paper-reviewer paths
    that route through get_paper_reviewer_client() helpers.
    """
    services_dir = Path(__file__).parent.parent / "app" / "services"
    capabilities_dir = Path(__file__).parent.parent / "app" / "capabilities"

    offenders: list[str] = []
    for root in (services_dir, capabilities_dir):
        for path in root.rglob("*.py"):
            if path.name == "ai_client.py":
                continue  # the definition file is allowed
            text = path.read_text()
            for line_no, line in enumerate(text.splitlines(), start=1):
                if "OpenAIClient(" in line:
                    # Whitelist: the gated helper itself
                    if "_paper_reviewer_client" in line or "get_paper_reviewer_client" in line:
                        continue
                    offenders.append(f"{path.relative_to(services_dir.parent.parent)}:{line_no}: {line.strip()}")

    assert not offenders, (
        "Direct OpenAIClient() instantiation found outside the gated paper-reviewer "
        "helper. These bypass CLOUD_AI_PROVIDER and leak to OpenAI. Move to "
        "get_cloud_client() or get_paper_reviewer_client():\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.asyncio
async def test_ingest_propagates_privacy_tag_to_entry(db_session, sample_project):
    """Privacy tag from user_tags must land in MemoryEntry.metadata_['tags']."""
    from app.services import file_ingest_service
    from app.services.file_ingest_service import ingest_file
    from app.services.privacy_tags import LOCAL_ONLY

    # Stub out auto_tag to avoid a real cloud AI call in this unit test.
    # The contract under test is tag propagation, not AI tagging.
    async def _fake_auto_tag(filename, text_preview, mime_type):
        return {"tags": ["data", "csv"], "summary": "test csv"}

    with patch.object(file_ingest_service, "auto_tag", side_effect=_fake_auto_tag):
        entry = await ingest_file(
            project_id=sample_project.id,
            filename="results.csv",
            content_bytes=b"col_a,col_b\n1,2\n3,4\n",
            source="manual",
            mime_type="text/csv",
            user_tags=[LOCAL_ONLY],
            db=db_session,
        )

    tags = (entry.metadata_ or {}).get("tags", [])
    assert LOCAL_ONLY in tags, f"expected {LOCAL_ONLY} in {tags}"
