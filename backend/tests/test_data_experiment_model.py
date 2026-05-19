import pytest
from sqlalchemy import select
from app.models.data_experiment import DataExperimentJob


@pytest.mark.asyncio
async def test_data_experiment_job_roundtrip(db_session, sample_user, sample_project):
    job = DataExperimentJob(
        user_id=sample_user.id,
        project_id=sample_project.id,
        sidecar_job_id="sc-123",
        objective="improve AUC",
        dataset_ref="hf:acme/widgets",
        status="queued",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    assert job.id is not None
    assert job.status == "queued"
    assert job.score is None
    assert job.result_node_id is None

    got = (await db_session.execute(
        select(DataExperimentJob).where(DataExperimentJob.id == job.id)
    )).scalar_one()
    assert got.objective == "improve AUC"
