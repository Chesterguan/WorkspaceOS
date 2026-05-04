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


import json
from app.services.knowledge_extractor import _extract_structured, ExtractedNode


@pytest.mark.asyncio
async def test_extract_structured_parses_json():
    payload = {
        "nodes": [
            {"node_type": "decision", "title": "Use pgvector",
             "content": "Use pgvector instead of Pinecone for vector search.",
             "confidence": 0.9, "rationale": "user said so"},
            {"node_type": "rejection", "title": "Pinecone",
             "content": "Pinecone rejected — managed-only.",
             "confidence": 0.85, "rationale": "..."},
        ],
        "edges_within_turn": [{"from_idx": 1, "to_idx": 0, "edge_type": "rejects"}],
    }
    ai = FakeAI(json.dumps(payload))
    result = await _extract_structured(ai, user="...", ai_response="...",
                                       conversation_kind="cofounder", recent_turns=[])
    assert len(result.nodes) == 2
    assert result.nodes[0].node_type == "decision"
    assert result.edges_within_turn[0]["edge_type"] == "rejects"


@pytest.mark.asyncio
async def test_extract_structured_handles_garbage():
    ai = FakeAI("not even close to json")
    result = await _extract_structured(ai, user="x", ai_response="y",
                                       conversation_kind="cofounder", recent_turns=[])
    assert result.nodes == []
    assert result.edges_within_turn == []


@pytest.mark.asyncio
async def test_extract_structured_ignores_invalid_node_types():
    payload = {
        "nodes": [
            {"node_type": "decision", "title": "ok", "content": "valid"},
            {"node_type": "wishful_thinking", "title": "bad", "content": "invalid type"},
        ],
        "edges_within_turn": [],
    }
    ai = FakeAI(json.dumps(payload))
    result = await _extract_structured(ai, user="x", ai_response="y",
                                       conversation_kind="cofounder", recent_turns=[])
    assert len(result.nodes) == 1
    assert result.nodes[0].node_type == "decision"
