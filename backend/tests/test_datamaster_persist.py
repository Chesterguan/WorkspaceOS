import uuid
import pytest
from sqlalchemy import select
from app.models.knowledge import KnowledgeNode, KnowledgeEdge
from app.capabilities.datamaster_runner import assemble_brief, persist_result


@pytest.mark.asyncio
async def test_assemble_brief_includes_nodes_and_objective(
    db_session, sample_user, sample_project
):
    node = KnowledgeNode(
        user_id=sample_user.id, project_id=sample_project.id,
        node_type="claim", title="Data leakage suspected",
        content="val split overlaps train", source_refs=[], metadata_={},
        created_by="manual",
    )
    db_session.add(node)
    await db_session.commit()

    brief, seed_ids = await assemble_brief(
        db_session, sample_user.id, sample_project.id, "boost AUC"
    )
    assert "boost AUC" in brief
    assert "Data leakage suspected" in brief
    assert node.id in seed_ids


@pytest.mark.asyncio
async def test_assemble_brief_empty_kg_notes_no_context(
    db_session, sample_user, sample_project
):
    brief, seed_ids = await assemble_brief(
        db_session, sample_user.id, sample_project.id, "cold start"
    )
    assert "cold start" in brief
    assert "no prior context" in brief.lower()
    assert seed_ids == []


@pytest.mark.asyncio
async def test_persist_result_creates_experiment_node_and_edges(
    db_session, sample_user, sample_project
):
    seed = KnowledgeNode(
        user_id=sample_user.id, project_id=sample_project.id,
        node_type="claim", title="seed", content="x",
        source_refs=[], metadata_={}, created_by="manual",
    )
    db_session.add(seed)
    await db_session.commit()
    await db_session.refresh(seed)

    node_id = await persist_result(
        db_session,
        user_id=sample_user.id,
        project_id=sample_project.id,
        objective="boost AUC",
        sidecar_job_id="sc-1",
        result={"score": 0.93, "pipeline_summary_md": "## Pipeline\nfoo",
                "artifacts": [{"name": "loader.py", "uri": "s3://x"}]},
        seed_node_ids=[seed.id],
    )
    exp = (await db_session.execute(
        select(KnowledgeNode).where(KnowledgeNode.id == node_id)
    )).scalar_one()
    assert exp.node_type == "experiment"
    assert exp.title == "boost AUC"
    assert "0.93" in exp.content
    assert exp.created_by == "capability"

    edges = (await db_session.execute(
        select(KnowledgeEdge).where(KnowledgeEdge.source_node_id == node_id)
    )).scalars().all()
    assert len(edges) == 1
    assert edges[0].target_node_id == seed.id
    assert edges[0].edge_type == "derived_from"


@pytest.mark.asyncio
async def test_persist_result_is_idempotent_on_duplicate_edges(
    db_session, sample_user, sample_project
):
    seed = KnowledgeNode(
        user_id=sample_user.id, project_id=sample_project.id,
        node_type="claim", title="seed-dup", content="x",
        source_refs=[], metadata_={}, created_by="manual",
    )
    db_session.add(seed)
    await db_session.commit()
    await db_session.refresh(seed)

    common = dict(
        user_id=sample_user.id, project_id=sample_project.id,
        objective="dup run", sidecar_job_id="sc-d",
        result={"score": 0.5, "pipeline_summary_md": "p", "artifacts": []},
        seed_node_ids=[seed.id, seed.id],  # same target twice -> one edge
    )
    node_id = await persist_result(db_session, **common)
    assert node_id is not None
    edges = (await db_session.execute(
        select(KnowledgeEdge).where(KnowledgeEdge.source_node_id == node_id)
    )).scalars().all()
    assert len(edges) == 1  # duplicate (source,target,derived_from) collapsed
