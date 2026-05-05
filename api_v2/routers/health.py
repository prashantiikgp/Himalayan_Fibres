"""GET /api/v2/health — liveness probe.

No auth required. Returns 200 with a simple JSON payload as long as the
process is up. Used by Phase 0 verification step 8.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "himalayan-fibers-api-v2", "version": "2.0.0-phase0"}
