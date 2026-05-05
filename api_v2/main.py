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

from api_v2.routers import (  # noqa: E402
    auth,
    broadcasts,
    contacts,
    dashboard,
    email_send,
    email_templates,
    flows,
    health,
    jobs,
    wa,
)

log = logging.getLogger(__name__)

# Fail-closed by default (review fix M1): APP_PASSWORD must be set, OR
# APP_OPEN_ACCESS=true must be explicitly opted into. Refusing to silently
# expose the API is the safe default — v1's open-by-default was inherited
# accidentally and shouldn't carry into v2.
_APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
_OPEN_ACCESS = os.getenv("APP_OPEN_ACCESS", "").strip().lower() in {"1", "true", "yes"}
if not _APP_PASSWORD and not _OPEN_ACCESS:
    raise SystemExit(
        "ERROR: APP_PASSWORD is unset and APP_OPEN_ACCESS is not enabled.\n"
        "  -> Set APP_PASSWORD as a Space Secret (recommended), OR\n"
        "  -> Set APP_OPEN_ACCESS=true to explicitly opt into open access.\n"
        "Refusing to start with a silently-unauthenticated API."
    )
if _OPEN_ACCESS and not _APP_PASSWORD:
    log.warning(
        "API IS OPEN - APP_OPEN_ACCESS=true and APP_PASSWORD is unset. "
        "All /api/v2/* routes are world-readable. Set APP_PASSWORD before "
        "exposing this Space publicly."
    )

# Initialize shared DB (creates tables if missing — same call v1 makes).
from services.database import ensure_db_ready  # type: ignore[import-not-found]  # noqa: E402

ensure_db_ready()

# Apply additive auto-migrations (Phase 3.1b.2 onward) — only safe
# `ADD COLUMN nullable` ALTERs that fit STANDARDS §2's "Allowed" list.
from api_v2.services.auto_migrations import run_all as run_auto_migrations  # noqa: E402

run_auto_migrations()

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

from contextlib import asynccontextmanager  # noqa: E402

from api_v2.services.scheduler import (  # noqa: E402
    enabled_in_env as scheduler_enabled,
    scheduler_loop,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):  # noqa: ANN001
    """Start the scheduler loop on app startup, cancel on shutdown."""
    import asyncio as _asyncio

    task = None
    if scheduler_enabled():
        # Review fix #5: refuse to start the scheduler if a required
        # column is missing — it would crash every tick otherwise.
        from api_v2.services.auto_migrations import required_columns_present

        ok, missing = required_columns_present()
        if not ok:
            log.error(
                "Scheduler disabled — required columns missing: %s. "
                "Run scripts/migrations/2026_05_05_add_broadcast_scheduled_at.py "
                "or check the auto-migration logs.",
                missing,
            )
            try:
                import sentry_sdk  # type: ignore[import-not-found]

                sentry_sdk.capture_message(
                    f"v2 scheduler disabled — missing columns: {missing}",
                    level="error",
                )
            except ImportError:
                pass
        else:
            # Phase 7.7 — re-arm any flow membership whose claim was
            # interrupted by a previous Space restart (status='active'
            # AND next_fire_at IS NULL). Runs once before the scheduler
            # starts so the first tick picks them up. Idempotent.
            try:
                from api_v2.services.flows_engine_v2 import reap_stranded_memberships

                reap_result = reap_stranded_memberships()
                if reap_result.get("reaped"):
                    log.info(
                        "Reaper: re-armed %d stranded flow membership(s)",
                        reap_result["reaped"],
                    )
            except Exception:
                log.exception("Stranded-membership reaper failed (non-fatal)")

            task = _asyncio.create_task(scheduler_loop())
            log.info("Phase 3.1b.2 scheduler started")
    else:
        log.info("Scheduler disabled by HF_SCHEDULER_ENABLED=false")

    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except Exception:
                pass


app = FastAPI(
    title="Himalayan Fibres Dashboard API v2",
    version="2.0.0-phase0",
    description=(
        "JSON API for the Vite + Shadcn dashboard at vite_dashboard/. "
        "Reuses domain logic from hf_dashboard/services/."
    ),
    lifespan=lifespan,
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
app.include_router(contacts.router, prefix="/api/v2", tags=["contacts"])
app.include_router(wa.router, prefix="/api/v2/wa", tags=["wa"])
app.include_router(broadcasts.router, prefix="/api/v2", tags=["broadcasts"])
app.include_router(flows.router, prefix="/api/v2", tags=["flows"])
# Phase 7.7 — flow membership endpoints (POST /flow-memberships/{id}/stop +
# GET /contacts/{id}/flow-memberships) live alongside flows under /api/v2.
app.include_router(flows.membership_router, prefix="/api/v2")
app.include_router(jobs.router, prefix="/api/v2", tags=["jobs"])
app.include_router(
    email_templates.router, prefix="/api/v2", tags=["email_templates"]
)
app.include_router(email_send.router, prefix="/api/v2", tags=["email_send"])

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
