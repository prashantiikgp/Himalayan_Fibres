"""FastAPI entry point for api_v2.

Boot order:
  1. Add hf_dashboard/ to sys.path so `services.X` imports resolve
  2. Load .env (only matters in local dev; HF Space uses Space Secrets)
  3. Initialize the database (shared models with v1)
  4. Wire Sentry
  5. Register routers
  6. Mount the built Vite SPA at /

Per STANDARDS §1, auth uses Bearer tokens validated against APP_PASSWORD.
Per STANDARDS production-readiness principle, validation errors are
fail-loud — we never return 200 with bogus data.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Make hf_dashboard/services, /engines, /loader importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_HF_DASHBOARD = _REPO_ROOT / "hf_dashboard"
if _HF_DASHBOARD.exists() and str(_HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_HF_DASHBOARD))

# Local dev .env (HF Space secrets work without this file).
try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

import sentry_sdk  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from api_v2.routers import auth, dashboard, health  # noqa: E402

log = logging.getLogger(__name__)

# Initialize shared DB (creates tables if missing — same call v1 makes).
from services.database import ensure_db_ready  # type: ignore[import-not-found]  # noqa: E402

ensure_db_ready()

# Sentry — production observability per STANDARDS §3.
_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        environment=os.getenv("APP_ENV", "production"),
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    log.info("Sentry initialized")
else:
    log.warning("SENTRY_DSN not set — error reporting disabled")

app = FastAPI(
    title="Himalayan Fibres Dashboard API v2",
    version="2.0.0-phase0",
    description=(
        "JSON API for the Vite + Shadcn dashboard at vite_dashboard/. "
        "Reuses domain logic from hf_dashboard/services/."
    ),
)

# CORS — local dev only; in prod the SPA is served from the same origin.
if os.getenv("APP_ENV", "development") != "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:4173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Routers — all under /api/v2.
app.include_router(health.router, prefix="/api/v2")
app.include_router(auth.router, prefix="/api/v2/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/api/v2", tags=["dashboard"])

# Static SPA mount — built dist/ from vite_dashboard.
# In dev (where dist/ doesn't exist), this is skipped silently.
_SPA_DIST = _REPO_ROOT / "vite_dashboard" / "dist"
if _SPA_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_SPA_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        """SPA catch-all — every non-API route serves index.html so React Router
        handles the path on the client."""
        index = _SPA_DIST / "index.html"
        if not index.exists():  # pragma: no cover
            raise FileNotFoundError("vite_dashboard/dist/index.html missing")
        return FileResponse(str(index))
