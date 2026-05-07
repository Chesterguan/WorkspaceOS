import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.services.knowledge_extractor import (
    _classify_extractable, _extract_structured, _decide_dedup_action,
    DedupAction, ExtractedNode, ExtractionResult, extract_from_chat_turn,
)
from app.models.knowledge import KnowledgeNode, KnowledgeEdge
from app.models.chat import ChatMessage


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




def test_dedup_above_high_threshold_merges():
    action = _decide_dedup_action(best_score=0.95, same_type=True)
    assert action.kind == "merge"


def test_dedup_high_score_but_different_type_creates_with_related_edge():
    action = _decide_dedup_action(best_score=0.95, same_type=False)
    assert action.kind == "create_with_edge"
    assert action.edge_type == "related_to"


def test_dedup_mid_threshold_creates_with_refines_edge_when_same_type():
    action = _decide_dedup_action(best_score=0.85, same_type=True)
    assert action.kind == "create_with_edge"
    assert action.edge_type == "refines"


def test_dedup_mid_threshold_creates_with_related_when_diff_type():
    action = _decide_dedup_action(best_score=0.85, same_type=False)
    assert action.kind == "create_with_edge"
    assert action.edge_type == "related_to"


def test_dedup_below_low_threshold_creates_standalone():
    action = _decide_dedup_action(best_score=0.5, same_type=False)
    assert action.kind == "create"
    assert action.edge_type is None


def test_dedup_no_match_creates_standalone():
    action = _decide_dedup_action(best_score=None, same_type=False)
    assert action.kind == "create"


# ---------------------------------------------------------------------------
# Integration test: persistence + within-turn edges
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_persists_nodes_and_within_turn_edges(db_session, sample_user, sample_project):
    """End-to-end: chat turn produces nodes + within-turn edges in DB."""
    user_msg = ChatMessage(
        project_id=sample_project.id, role="user",
        content="should we use pgvector or pinecone?",
    )
    ai_msg = ChatMessage(
        project_id=sample_project.id, role="assistant",
        content="Use pgvector — Pinecone is managed-only and we want SQL access.",
    )
    db_session.add_all([user_msg, ai_msg])
    await db_session.commit()
    await db_session.refresh(user_msg)
    await db_session.refresh(ai_msg)

    fake_yes = FakeAI("YES")  # stage 1 classifier
    extraction_result = ExtractionResult(
        nodes=[
            ExtractedNode(node_type="decision", title="Use pgvector",
                          content="Use pgvector for vector search.", confidence=0.9),
            ExtractedNode(node_type="rejection", title="Pinecone rejected",
                          content="Pinecone rejected — managed-only, no SQL.", confidence=0.85),
        ],
        edges_within_turn=[{"from_idx": 1, "to_idx": 0, "edge_type": "rejects"}],
    )

    # Use orthogonal unit vectors so cosine similarity = 0 → no false merges.
    # Node 0: leading 1.0; Node 1: trailing 1.0 — they are orthogonal.
    embed_calls = [[1.0] + [0.0] * 767, [0.0] * 767 + [1.0]]
    embed_iter = iter(embed_calls)

    async def _fake_embed(_text: str):
        return next(embed_iter)

    with patch("app.services.knowledge_extractor.get_cloud_client", return_value=fake_yes), \
         patch("app.services.knowledge_extractor._extract_structured",
               new=AsyncMock(return_value=extraction_result)), \
         patch("app.services.knowledge_extractor._embed", new=_fake_embed):
        await extract_from_chat_turn(
            user_id=sample_user.id, project_id=sample_project.id,
            user_message=user_msg, ai_message=ai_msg,
            conversation_kind="cofounder", db=db_session,
        )

    nodes = (await db_session.execute(
        select(KnowledgeNode).where(KnowledgeNode.user_id == sample_user.id)
    )).scalars().all()
    assert len(nodes) == 2
    assert {n.node_type for n in nodes} == {"decision", "rejection"}

    edges = (await db_session.execute(
        select(KnowledgeEdge).where(KnowledgeEdge.user_id == sample_user.id)
    )).scalars().all()
    assert len(edges) == 1
    assert edges[0].edge_type == "rejects"


@pytest.mark.asyncio
async def test_promote_manual_creates_node_with_user_supplied_fields(db_session, sample_user, sample_project):
    from app.services.knowledge_extractor import promote_manual
    from app.schemas.knowledge import SourceRef

    with patch("app.services.knowledge_extractor._embed", new=AsyncMock(return_value=[0.0]*768)):
        node = await promote_manual(
            user_id=sample_user.id, project_id=sample_project.id,
            source=SourceRef(kind="manual", note="from chat msg X"),
            suggested_type="decision",
            title="Manual decision",
            content="We decided to do thing.",
            db=db_session,
        )
    assert node.node_type == "decision"
    assert node.title == "Manual decision"
    assert node.created_by == "manual_promote"
