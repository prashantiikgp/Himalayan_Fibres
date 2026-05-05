"""Smoke tests for /api/v2/flows (Phase 5.0)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from api_v2.main import app

    return TestClient(app)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test_secret"}


def _seed_flow(channel: str = "email", active: bool = True) -> int:
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import Flow  # type: ignore[import-not-found]

    stamp = int(time.time() * 1000)
    db = get_db()
    try:
        f = Flow(
            name=f"phase5_flow_{stamp}",
            description="seeded flow",
            channel=channel,
            steps=[
                {"day": 0, "template_slug": "step_one"},
                {"day": 3, "template_slug": "step_two"},
            ],
            is_active=active,
        )
        db.add(f)
        db.commit()
        db.refresh(f)
        return f.id
    finally:
        db.close()


def _seed_flow_runs(flow_id: int, n: int = 3) -> list[int]:
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import FlowRun  # type: ignore[import-not-found]

    db = get_db()
    try:
        ids: list[int] = []
        for i in range(n):
            r = FlowRun(
                flow_id=flow_id,
                segment_id=f"segment_{i}",
                started_at=datetime.now(timezone.utc) - timedelta(hours=i),
                current_step=i,
                status="active" if i == 0 else "completed",
                total_contacts=10 + i,
                total_sent=10 + i,
                total_failed=0,
            )
            db.add(r)
            db.flush()
            ids.append(r.id)
        db.commit()
        return ids
    finally:
        db.close()


def test_list_flows(client: TestClient, auth_headers: dict[str, str]) -> None:
    fid = _seed_flow()
    res = client.get("/api/v2/flows", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    seeded = next((f for f in body["flows"] if f["id"] == fid), None)
    assert seeded is not None
    assert seeded["step_count"] == 2
    assert seeded["channel"] in {"email", "whatsapp"}
    assert seeded["is_active"] is True


def test_list_flows_active_only(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    active_id = _seed_flow(active=True)
    inactive_id = _seed_flow(active=False)

    body = client.get("/api/v2/flows?active_only=true", headers=auth_headers).json()
    ids = {f["id"] for f in body["flows"]}
    assert active_id in ids
    assert inactive_id not in ids


def test_list_flows_channel_filter(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    email_id = _seed_flow(channel="email")
    wa_id = _seed_flow(channel="whatsapp")

    body = client.get("/api/v2/flows?channel=email", headers=auth_headers).json()
    ids = {f["id"] for f in body["flows"]}
    assert email_id in ids
    assert wa_id not in ids


def test_list_flows_invalid_channel_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get("/api/v2/flows?channel=fax", headers=auth_headers)
    assert res.status_code == 400


def test_list_flow_runs(client: TestClient, auth_headers: dict[str, str]) -> None:
    fid = _seed_flow()
    _seed_flow_runs(fid, n=3)

    res = client.get(f"/api/v2/flows/{fid}/runs", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 3
    # Newest run first
    assert body["runs"][0]["status"] == "active"


def test_list_flow_runs_unknown_flow_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get("/api/v2/flows/999999/runs", headers=auth_headers)
    assert res.status_code == 404


def test_flows_require_auth(client: TestClient) -> None:
    assert client.get("/api/v2/flows").status_code == 401
    assert client.get("/api/v2/flows/1/runs").status_code == 401
