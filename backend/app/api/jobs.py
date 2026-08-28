from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.security import get_current_admin_principal
from app.db import get_db
from app.models.jobs import ScheduledJobRun
from app.schemas import JobRunOut, JobTriggerResult
from app.services.jobs import JOB_FREQUENCIES, JOB_REGISTRY

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRunOut])
async def list_jobs(session: AsyncSession = Depends(get_db), _admin=Depends(get_current_admin_principal)):
    rows = (
        await session.execute(select(ScheduledJobRun).order_by(ScheduledJobRun.started_at.desc()).limit(100))
    ).scalars().all()
    return rows


@router.post("/{job_name}/run", response_model=JobTriggerResult)
async def run_job(
    job_name: str,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _admin=Depends(get_current_admin_principal),
):
    if job_name not in JOB_REGISTRY:
        raise HTTPException(404, f"Unknown job '{job_name}'")
    result = await JOB_REGISTRY[job_name](session, settings)
    return JobTriggerResult(job_name=job_name, result=result)


@router.get("/diagnostics")
async def job_diagnostics(
    session: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin_principal),
):
    rows = (
        await session.execute(
            select(ScheduledJobRun).order_by(ScheduledJobRun.started_at.desc()).limit(100)
        )
    ).scalars().all()
    latest = {}
    for row in rows:
        latest.setdefault(row.job_name, row)
    return {
        "registered_jobs": list(JOB_REGISTRY),
        "frequencies": JOB_FREQUENCIES,
        "worker": {"state": "separate_process", "scheduler_managed": True},
        "latest_runs": [JobRunOut.model_validate(row).model_dump(mode="json") for row in latest.values()],
    }
