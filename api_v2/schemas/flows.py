"""Pydantic schemas for /api/v2/flows (Phase 5.0 + Phase 7.7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FlowOut(BaseModel):
    """One flow row in the list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str | None = None
    description: str
    # Phase 7.7 widens to multi (multi-channel flows).
    channel: Literal["email", "whatsapp", "multi"]
    is_active: bool
    step_count: int
    """Computed from len(steps) — the editor exposes the full steps list
    via FlowDetail (next phase). The list endpoint just shows the
    summary count to keep the wire payload light."""
    trigger_type: str = "manual"
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    active_count: int = 0
    """Number of `flow_memberships` rows in {active, waiting_event, paused}.
    Populated by the list endpoint via a single GROUP BY query."""
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


# ─────────────────────────────────────────────────────────────────────
# Phase 7.7 — memberships
# ─────────────────────────────────────────────────────────────────────


class FlowMembershipOut(BaseModel):
    """One per-contact membership in a flow — drawer's Flows tab + flow
    detail page."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    flow_id: int
    flow_name: str = ""
    flow_slug: str | None = None
    contact_id: str
    contact_name: str = ""
    contact_email: str | None = None
    status: str
    current_step_index: int
    total_steps: int = 0
    started_at: datetime
    last_step_at: datetime | None = None
    next_fire_at: datetime | None = None
    trigger_source: str
    trigger_actor: str = ""
    error: str = ""


class FlowMembershipsResponse(BaseModel):
    memberships: list[FlowMembershipOut]
    total: int


class FlowMembershipCreate(BaseModel):
    """Body for POST /api/v2/flows/{flow_id}/memberships."""

    contact_id: str
    actor: str = "user"


class FlowStepRunOut(BaseModel):
    """Per-step audit row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    membership_id: int
    step_index: int
    channel: Literal["email", "whatsapp"]
    fired_at: datetime
    status: str
    template_slug: str
    message_ref: str = ""
    error: str = ""


class FlowStepRunsResponse(BaseModel):
    step_runs: list[FlowStepRunOut]
    total: int


class MarkSampleShippedRequest(BaseModel):
    """Body for POST /api/v2/contacts/{id}/mark-sample-shipped — see
    PLAN_flows §7.1. Adds tag `samples_shipped` and writes the tracking
    payload onto any waiting Sample Dispatch membership in the same
    transaction."""

    tracking_id: str = Field(min_length=1, max_length=128)
    courier_name: str = Field(min_length=1, max_length=64)


class MarkSampleShippedResponse(BaseModel):
    tag_added: bool
    memberships_updated: list[int]
    new_memberships_from_trigger: int
