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
