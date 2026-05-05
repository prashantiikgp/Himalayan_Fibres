"""/api/v2/jobs — job-state polling (Phase 3.1b.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api_v2.deps import require_auth
from api_v2.schemas.jobs import JobStatusResponse
from api_v2.services.job_store import get_job_store

router = APIRouter(tags=["jobs"], dependencies=[Depends(require_auth)])


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    """Poll a job's progress + result.

    The job store is in-memory and process-local; if the HF Space has
    been rebuilt since the job was created, the call returns 404 even
    though the underlying email sends may have completed (their
    `EmailSend` rows persist in the DB regardless).
    """
    store = get_job_store()
    state = store.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**store.to_dict(state))
