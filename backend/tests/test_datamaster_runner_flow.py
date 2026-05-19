import uuid
import pytest
from sqlalchemy import select

import app.capabilities.datamaster_runner as R
from app.capabilities import datamaster_sidecar as SC
from app.models.data_experiment import DataExperimentJob
from app.models.knowledge import KnowledgeNode


@pytest.mark.asyncio
async def test_run_job_happy_path_persists_experiment_and_marks_done(
    db_session, sample_user, sample_project, monkeypatch
):
    events = []
    monkeypatch.setattr(R, "emit",
                         lambda *a, **k: events.append((a, k)))

    async def fake_submit(base, token, body): return None

    async def fake_stream(base, token, jid):
        yield {"type": "phase", "data": {"name": "explore"}}
        yield {"type": "node", "data": {"color": "red", "summary": "ext"}}
        yield {"type": "done",
               "data": {"score": 0.88, "pipeline_summary_md": "## P",
                        "artifacts": []}}

    monkeypatch.setattr(SC, "submit_job", fake_submit)
    monkeypatch.setattr(SC, "stream_job", fake_stream)

    job = DataExperimentJob(
        user_id=sample_user.id, project_id=sample_project.id,
        sidecar_job_id="sc-x", objective="boost AUC",
        dataset_ref="hf:a/b", status="queued",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    await R._run_job(
        job_id=job.id, base_url="http://sidecar", token=None,
        max_minutes=5, brief="# brief", seed_node_ids=[],
        dataset={"kind": "hf", "ref": "a/b"}, objective="boost AUC",
        _db=db_session,
    )

    refreshed = (await db_session.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job.id)
    )).scalar_one()
    assert refreshed.status == "done"
    assert refreshed.score == 0.88
    assert refreshed.result_node_id is not None
    exp = (await db_session.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.id == refreshed.result_node_id)
    )).scalar_one()
    assert exp.node_type == "experiment"


@pytest.mark.asyncio
async def test_run_job_sidecar_error_marks_error_no_node(
    db_session, sample_user, sample_project, monkeypatch
):
    monkeypatch.setattr(R, "emit", lambda *a, **k: None)

    async def fake_submit(base, token, body): return None

    async def fake_stream(base, token, jid):
        yield {"type": "error", "data": {"message": "sandbox OOM"}}

    monkeypatch.setattr(SC, "submit_job", fake_submit)
    monkeypatch.setattr(SC, "stream_job", fake_stream)

    job = DataExperimentJob(
        user_id=sample_user.id, project_id=sample_project.id,
        sidecar_job_id="sc-e", objective="x", dataset_ref="hf:a/b",
        status="queued",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    await R._run_job(
        job_id=job.id, base_url="http://sidecar", token=None,
        max_minutes=5, brief="# b", seed_node_ids=[],
        dataset={"kind": "hf", "ref": "a/b"}, objective="x",
        _db=db_session,
    )
    refreshed = (await db_session.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job.id)
    )).scalar_one()
    assert refreshed.status == "error"
    assert "sandbox OOM" in (refreshed.error or "")
    assert refreshed.result_node_id is None


def test_spawn_run_job_retains_task_reference(monkeypatch):
    import asyncio as _aio

    captured = {}

    def fake_create_task(coro):
        t = _DummyTask(coro)
        captured["task"] = t
        return t

    class _DummyTask:
        def __init__(self, coro):
            self._cb = None
            coro.close()  # don't actually run

        def add_done_callback(self, cb):
            self._cb = cb

    monkeypatch.setattr(R.asyncio, "create_task", fake_create_task)
    R._spawn_run_job(job_id=None, base_url="x", token=None, max_minutes=1,
                     brief="b", seed_node_ids=[], dataset={}, objective="o")
    assert captured["task"] in R._background_tasks
    captured["task"]._cb(captured["task"])  # simulate completion
    assert captured["task"] not in R._background_tasks


@pytest.mark.asyncio
async def test_handler_rejects_invalid_dataset(
    db_session, sample_user, monkeypatch
):
    monkeypatch.setattr(R, "emit", lambda *a, **k: None)
    out = await R.run_data_experiment_handler(
        {"project_id": str(uuid.uuid4()), "objective": "x",
         "dataset_ref": "/etc/passwd"},
        db_session, sample_user.id,
    )
    assert out["ok"] is False
    assert "dataset" in out["toast"].lower()
