"""In-memory job store for async broadcasts.

A bounded dict mapping job_id → JobState. Lives for the lifetime of the
api_v2 process; if the HF Space rebuilds, in-flight jobs are forgotten
(the underlying email sends complete and persist via EmailSend rows
either way — only the progress UI loses its handle). Phase 5 may
promote this to a DB-backed table.

Thread-safety: PoolingExecutor + BackgroundTasks both call into
`update()`, but the GIL plus the trivial dict mutations are sufficient
here. If we move to a real worker queue later, swap for a Lock-guarded
implementation.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Literal

JobStatus = Literal["queued", "running", "done", "failed"]


@dataclass
class JobState:
    job_id: str
    job_type: str
    status: JobStatus = "queued"
    progress: int = 0
    """0-100. 0 while queued, 100 when done."""
    message: str = ""
    """Human-readable last-known status text."""
    result: dict | None = None
    """Final payload — populated when status == done|failed."""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._max_jobs = 256

    def create(self, job_type: str, message: str = "") -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = JobState(
                job_id=job_id, job_type=job_type, message=message,
            )
            self._evict_if_needed()
        return job_id

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        progress: int | None = None,
        message: str | None = None,
        result: dict | None = None,
    ) -> None:
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return
            if status is not None:
                state.status = status
            if progress is not None:
                state.progress = max(0, min(100, int(progress)))
            if message is not None:
                state.message = message
            if result is not None:
                state.result = result
            state.updated_at = time.time()

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def to_dict(self, state: JobState) -> dict:
        return asdict(state)

    def _evict_if_needed(self) -> None:
        # Caller holds the lock.
        if len(self._jobs) <= self._max_jobs:
            return
        # Drop the oldest done/failed jobs first.
        terminal = [
            (jid, s) for jid, s in self._jobs.items() if s.status in {"done", "failed"}
        ]
        terminal.sort(key=lambda kv: kv[1].updated_at)
        for jid, _ in terminal:
            if len(self._jobs) <= self._max_jobs:
                break
            del self._jobs[jid]


_singleton: JobStore | None = None


def get_job_store() -> JobStore:
    """Module-level singleton — same instance for the lifetime of the
    api_v2 process. Survives Depends() injection chains."""
    global _singleton
    if _singleton is None:
        _singleton = JobStore()
    return _singleton
