"""Pydantic schemas for /api/v2/jobs (Phase 3.1b.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: Literal["queued", "running", "done", "failed"]
    progress: int
    message: str
    result: dict[str, Any] | None
