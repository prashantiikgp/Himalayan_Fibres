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

# Reuse v1's cached helpers — no duplication of business logic.
from pages.home import (  # type: ignore[import-not-found]
    _activity_feed_cached,
    _home_counters_cached,
    _lifecycle_counts_cached,
)
from services.contact_schema import get_lifecycle_stages  # type: ignore[import-not-found]

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
        lifecycle=lifecycle,
        activity=activity,
    )


@router.get("/system/status", response_model=SystemStatus)
async def system_status(_auth: Annotated[None, Depends(require_auth)]) -> SystemStatus:
    return SystemStatus(
        gmail_configured=bool(os.getenv("GMAIL_REFRESH_TOKEN", "")),
        wa_configured=bool(os.getenv("WA_TOKEN", "")),
    )
