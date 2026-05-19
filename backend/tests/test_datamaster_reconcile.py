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
