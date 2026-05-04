import pytest
from unittest.mock import AsyncMock, patch

from app.models.knowledge import KnowledgeNode, KnowledgeEdge
from app.services.knowledge_service import (
    search_knowledge, list_recent_nodes, get_node_with_neighbors,
)


@pytest.mark.asyncio
async def test_search_returns_user_scoped_results(db_session, sample_user):
    db_session.add_all([
        KnowledgeNode(user_id=sample_user.id, node_type="decision",
                      title="pgvector", content="use pgvector for search",
                      created_by="manual_promote"),
        KnowledgeNode(user_id=sample_user.id, node_type="claim",
                      title="bm25 helps", content="hybrid retrieval improves recall",
                      created_by="manual_promote"),
    ])
    await db_session.commit()

    with patch("app.services.knowledge_service._embed_query",
               new=AsyncMock(return_value=[0.0]*768)):
        hits = await search_knowledge(
            user_id=sample_user.id, query="pgvector", limit=5, db=db_session,
        )
    assert any(h.node.title == "pgvector" for h in hits)


@pytest.mark.asyncio
async def test_search_filters_archived(db_session, sample_user):
    db_session.add(KnowledgeNode(
        user_id=sample_user.id, node_type="claim",
        title="old finding", content="archived content about pgvector",
        archived=True, created_by="manual_promote",
    ))
    await db_session.commit()
    with patch("app.services.knowledge_service._embed_query",
               new=AsyncMock(return_value=[0.0]*768)):
        hits = await search_knowledge(
            user_id=sample_user.id, query="pgvector", limit=5, db=db_session,
        )
    assert all(not h.node.archived for h in hits)


@pytest.mark.asyncio
async def test_search_scopes_by_project_when_provided(db_session, sample_user, sample_project):
    db_session.add_all([
        KnowledgeNode(user_id=sample_user.id, project_id=sample_project.id,
                      node_type="decision", title="in-project decision",
                      content="this belongs to the project", created_by="manual_promote"),
        KnowledgeNode(user_id=sample_user.id, project_id=None,
                      node_type="decision", title="orphan decision",
                      content="cross-project, no project_id", created_by="manual_promote"),
    ])
    await db_session.commit()
    with patch("app.services.knowledge_service._embed_query",
               new=AsyncMock(return_value=[0.0]*768)):
        hits = await search_knowledge(
            user_id=sample_user.id, query="decision", limit=5, db=db_session,
            project_id=sample_project.id,
        )
    titles = [h.node.title for h in hits]
    assert "in-project decision" in titles
    assert "orphan decision" not in titles


@pytest.mark.asyncio
async def test_list_recent_nodes_user_scoped(db_session, sample_user):
    db_session.add_all([
        KnowledgeNode(user_id=sample_user.id, node_type="claim",
                      title="x", content="y", created_by="manual_promote"),
    ])
    await db_session.commit()
    nodes = await list_recent_nodes(user_id=sample_user.id, db=db_session)
    assert len(nodes) >= 1
    assert all(n.user_id == sample_user.id for n in nodes)


@pytest.mark.asyncio
async def test_get_node_with_neighbors_returns_graph(db_session, sample_user):
    a = KnowledgeNode(user_id=sample_user.id, node_type="claim",
                     title="A", content="claim a", created_by="manual_promote")
    b = KnowledgeNode(user_id=sample_user.id, node_type="claim",
                     title="B", content="claim b", created_by="manual_promote")
    db_session.add_all([a, b])
    await db_session.flush()
    db_session.add(KnowledgeEdge(
        user_id=sample_user.id, source_node_id=a.id, target_node_id=b.id,
        edge_type="supports", weight=1.0, created_by="manual_promote",
    ))
    await db_session.commit()

    nodes, edges = await get_node_with_neighbors(
        node_id=a.id, user_id=sample_user.id, db=db_session, depth=1,
    )
    assert {n.id for n in nodes} == {a.id, b.id}
    assert len(edges) == 1
    assert edges[0].edge_type == "supports"
