import pytest
from sqlalchemy import select
import app.capabilities.datamaster_runner as R
from app.capabilities import datamaster_sidecar as SC
from app.models.data_experiment import DataExperimentJob


@pytest.mark.asyncio
async def test_reconcile_marks_dead_running_job_error(
    db_session, sample_user, sample_project, monkeypatch
):
    monkeypatch.setattr(R, "emit", lambda *a, **k: None)

    async def fake_eff_cfg():
        return {"sidecar_base_url": "http://sidecar", "sidecar_token": None}

    async def fake_get_job(base, token, jid):
        raise RuntimeError("sidecar forgot this job after restart")

    monkeypatch.setattr(R, "effective_config", fake_eff_cfg)
    monkeypatch.setattr(SC, "get_job", fake_get_job)

    job = DataExperimentJob(
        user_id=sample_user.id, project_id=sample_project.id,
        sidecar_job_id="sc-dead", objective="x", dataset_ref="hf:a/b",
        status="running",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    await R.reconcile_running_jobs(_db=db_session)

    refreshed = (await db_session.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job.id)
    )).scalar_one()
    assert refreshed.status == "error"
    assert "restart" in (refreshed.error or "").lower()


@pytest.mark.asyncio
async def test_reconcile_persists_when_sidecar_confirms_done(
    db_session, sample_user, sample_project, monkeypatch
):
    monkeypatch.setattr(R, "emit", lambda *a, **k: None)

    async def fake_eff_cfg():
        return {"sidecar_base_url": "http://sidecar", "sidecar_token": None}

    async def fake_get_job(base, token, jid):
        return {"status": "done",
                "result": {"score": 0.77, "pipeline_summary_md": "p",
                           "artifacts": []}}

    monkeypatch.setattr(R, "effective_config", fake_eff_cfg)
    monkeypatch.setattr(SC, "get_job", fake_get_job)

    job = DataExperimentJob(
        user_id=sample_user.id, project_id=sample_project.id,
        sidecar_job_id="sc-ok", objective="recover me",
        dataset_ref="hf:a/b", status="running",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    await R.reconcile_running_jobs(_db=db_session)

    refreshed = (await db_session.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job.id)
    )).scalar_one()
    assert refreshed.status == "done"
    assert refreshed.score == 0.77
    assert refreshed.result_node_id is not None


@pytest.mark.asyncio
async def test_reconcile_one_bad_job_does_not_block_others(
    db_session, sample_user, sample_project, monkeypatch
):
    monkeypatch.setattr(R, "emit", lambda *a, **k: None)

    async def fake_eff_cfg():
        return {"sidecar_base_url": "http://sidecar", "sidecar_token": None}

    async def fake_get_job(base, token, jid):
        raise RuntimeError("sidecar forgot after restart")

    monkeypatch.setattr(R, "effective_config", fake_eff_cfg)
    monkeypatch.setattr(SC, "get_job", fake_get_job)

    j1 = DataExperimentJob(
        user_id=sample_user.id, project_id=sample_project.id,
        sidecar_job_id="b1", objective="a", dataset_ref="hf:a/b",
        status="running")
    j2 = DataExperimentJob(
        user_id=sample_user.id, project_id=sample_project.id,
        sidecar_job_id="b2", objective="b", dataset_ref="hf:a/b",
        status="running")
    db_session.add_all([j1, j2])
    await db_session.commit()
    await db_session.refresh(j1)
    await db_session.refresh(j2)

    await R.reconcile_running_jobs(_db=db_session)

    for jid in (j1.id, j2.id):
        r = (await db_session.execute(
            select(DataExperimentJob).where(DataExperimentJob.id == jid)
        )).scalar_one()
        assert r.status == "error"
        assert "restart" in (r.error or "").lower()
