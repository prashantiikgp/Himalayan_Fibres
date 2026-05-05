"""GET /api/v2/dashboard/home — KPIs + lifecycle + activity for the Home page.
GET /api/v2/system/status — Email + WhatsApp connection status.

Reuses the cached helpers from hf_dashboard/pages/home.py rather than
re-implementing the queries. That preserves the Plan D Phase 2b
optimizations and keeps v1 + v2 returning the same numbers.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api_v2.deps import require_auth

# Reuse the cached metric loaders — Phase 2.3 moved these out of
# pages/home.py (which top-level imports gradio) into services so
# api_v2 doesn't drag gradio into its dependency tree.
from services.home_metrics import (  # type: ignore[import-not-found]
    activity_feed_cached as _activity_feed_cached,
    home_counters_cached as _home_counters_cached,
    lifecycle_counts_cached as _lifecycle_counts_cached,
)
from services.contact_schema import get_lifecycle_stages  # type: ignore[import-not-found]
from services.database import get_db  # type: ignore[import-not-found]
from services.models import (  # type: ignore[import-not-found]
    EmailTemplate,
    WATemplate,
)

router = APIRouter()


class LifecycleEntry(BaseModel):
    id: str
    label: str
    icon: str
    color: str
    count: int


class ActivityEntry(BaseModel):
    timestamp: str = Field(description="ISO 8601 UTC timestamp")
    kind: str = Field(description='"email_sent" | "wa_sent" | "wa_received"')
    text: str


class HomeData(BaseModel):
    emails_today: int
    wa_today: int
    total: int
    wa_24h: int
    wa_ready: int
    opted_in: int
    pending: int
    email_campaigns: int
    wa_campaigns: int
    total_flows: int
    active_runs: int
    email_template_count: int
    """Active EmailTemplate rows. **B12 fix** — v1's home.py hardcoded
    'Templates: 7 email, 13 WA'; v2 reads from the DB."""
    wa_template_count: int
    """Approved, non-draft WATemplate rows."""
    lifecycle: list[LifecycleEntry]
    activity: list[ActivityEntry]


class SystemStatus(BaseModel):
    gmail_configured: bool
    wa_configured: bool


@router.get("/dashboard/home", response_model=HomeData)
async def dashboard_home(_auth: Annotated[None, Depends(require_auth)]) -> HomeData:
    counts = _home_counters_cached()
    lifecycle_map = _lifecycle_counts_cached()
    raw_activities = _activity_feed_cached(20)

    # **B12 fix**: count templates from the DB instead of the v1
    # hardcoded "7 email, 13 WA" pair. Cheap query — runs on every
    # /dashboard/home call but the table is tiny (~30 rows).
    db = get_db()
    try:
        email_tpl_count = (
            db.query(EmailTemplate).filter(EmailTemplate.is_active.is_(True)).count()
        )
        wa_tpl_count = (
            db.query(WATemplate)
            .filter(WATemplate.is_draft.is_(False))
            .filter(WATemplate.status == "APPROVED")
            .count()
        )
    finally:
        db.close()

    stages = get_lifecycle_stages()
    lifecycle = [
        LifecycleEntry(
            id=stage["id"],
            label=stage["label"],
            icon=stage["icon"],
            color=stage["color"],
            count=int(lifecycle_map.get(stage["id"], 0)),
        )
        for stage in stages
    ]

    activity = []
    for ts, kind, text in raw_activities:
        if ts is None:
            ts_iso = datetime.now(timezone.utc).isoformat()
        elif ts.tzinfo is None:
            ts_iso = ts.replace(tzinfo=timezone.utc).isoformat()
        else:
            ts_iso = ts.isoformat()
        activity.append(ActivityEntry(timestamp=ts_iso, kind=kind, text=text))

    return HomeData(
        emails_today=counts["emails_today"],
        wa_today=counts["wa_today"],
        total=counts["total"],
        wa_24h=counts["wa_24h"],
        wa_ready=counts["wa_ready"],
        opted_in=counts["opted_in"],
        pending=counts["pending"],
        email_campaigns=counts["email_campaigns"],
        wa_campaigns=counts["wa_campaigns"],
        total_flows=counts["total_flows"],
        active_runs=counts["active_runs"],
        email_template_count=email_tpl_count,
        wa_template_count=wa_tpl_count,
        lifecycle=lifecycle,
        activity=activity,
    )


@router.get("/system/status", response_model=SystemStatus)
async def system_status(_auth: Annotated[None, Depends(require_auth)]) -> SystemStatus:
    return SystemStatus(
        gmail_configured=bool(os.getenv("GMAIL_REFRESH_TOKEN", "")),
        wa_configured=bool(os.getenv("WA_TOKEN", "")),
    )
