"""Pydantic schemas for /api/v2/flows (Phase 5.0)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class FlowOut(BaseModel):
    """One flow row in the list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    channel: Literal["email", "whatsapp"]
    is_active: bool
    step_count: int
    """Computed from len(steps) — the editor exposes the full steps list
    via FlowDetail (next phase). The list endpoint just shows the
    summary count to keep the wire payload light."""
    created_at: datetime


class FlowsResponse(BaseModel):
    flows: list[FlowOut]
    total: int


class FlowRunOut(BaseModel):
    """One run row — for the recent-runs list under a flow."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    flow_id: int
    segment_id: str | None
    status: str
    current_step: int
    total_contacts: int
    total_sent: int
    total_failed: int
    started_at: datetime
    next_step_at: datetime | None


class FlowRunsResponse(BaseModel):
    runs: list[FlowRunOut]
    total: int
