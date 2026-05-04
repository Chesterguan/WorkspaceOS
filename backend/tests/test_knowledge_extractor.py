import pytest
from unittest.mock import AsyncMock, patch

from app.services.knowledge_extractor import _classify_extractable


class FakeAI:
    def __init__(self, response: str):
        self._r = response

    async def complete(self, system: str, user: str) -> str:
        return self._r


@pytest.mark.asyncio
async def test_classify_extractable_yes():
    ai = FakeAI("YES")
    result = await _classify_extractable(ai, user="we should ditch Pinecone", ai_response="agreed, use pgvector")
    assert result is True


@pytest.mark.asyncio
async def test_classify_extractable_no():
    ai = FakeAI("NO")
    result = await _classify_extractable(ai, user="hi", ai_response="hello, what's up?")
    assert result is False


@pytest.mark.asyncio
async def test_classify_extractable_normalizes_whitespace_and_case():
    ai = FakeAI("  yes.  ")
    result = await _classify_extractable(ai, user="x", ai_response="y")
    assert result is True


@pytest.mark.asyncio
async def test_classify_extractable_falls_back_to_no_on_garbage():
    ai = FakeAI("I don't know")
    result = await _classify_extractable(ai, user="x", ai_response="y")
    assert result is False
