"""Smoke tests for /api/v2/broadcasts (Phase 3.0 unified list)."""

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


def _seed_one_of_each() -> tuple[int, int]:
    """Seed one Broadcast (WA) + one Campaign (Email). Returns the two
    autoincrement IDs so tests can locate them by `wa-{id}` / `em-{id}`.
    """
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import Broadcast, Campaign  # type: ignore[import-not-found]

    stamp = int(time.time() * 1000)
    db = get_db()
    try:
        b = Broadcast(
            name=f"B6-test WA {stamp}",
            channel="whatsapp",
            template_id="welcome_message",
            segment_id="all_opted_in",
            status="completed",
            total_recipients=2,
            total_sent=2,
            total_failed=0,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(b)

        c = Campaign(
            name=f"B6-test Email {stamp}",
            template_slug="b2b_introduction",
            segment_id=None,
            status="sent",
            total_recipients=5,
            total_sent=5,
            total_failed=0,
            sent_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(c)
        db.commit()
        db.refresh(b)
        db.refresh(c)
        return b.id, c.id
    finally:
        db.close()


def test_list_broadcasts_unified(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Default returns rows from both tables, normalized into the same
    shape (Phase 3.0 read-side; foundation for the History tab)."""
    wa_id, em_id = _seed_one_of_each()
    res = client.get("/api/v2/broadcasts?page_size=200", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    ids = {b["id"] for b in body["broadcasts"]}
    assert f"wa-{wa_id}" in ids
    assert f"em-{em_id}" in ids
    # Channels mix
    channels = {b["channel"] for b in body["broadcasts"]}
    assert "whatsapp" in channels and "email" in channels


def test_list_broadcasts_email_filter_returns_email_only(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """**B6 fix verified at the DB layer.** Filtering by `channel=email`
    returns only Campaign rows; v1's broadcast_history page filtered
    only by `Broadcast` table so this returned zero — now it works.
    """
    _wa_id, em_id = _seed_one_of_each()
    res = client.get(
        "/api/v2/broadcasts?channel=email&page_size=200", headers=auth_headers
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert all(b["channel"] == "email" for b in body["broadcasts"])
    assert any(b["id"] == f"em-{em_id}" for b in body["broadcasts"])


def test_list_broadcasts_whatsapp_filter(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wa_id, _em_id = _seed_one_of_each()
    res = client.get(
        "/api/v2/broadcasts?channel=whatsapp&page_size=200", headers=auth_headers
    )
    assert res.status_code == 200
    body = res.json()
    assert all(b["channel"] == "whatsapp" for b in body["broadcasts"])
    assert any(b["id"] == f"wa-{wa_id}" for b in body["broadcasts"])


def test_list_broadcasts_status_filter(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Status filter applies to both tables."""
    _seed_one_of_each()
    res = client.get(
        "/api/v2/broadcasts?status=sent&page_size=200", headers=auth_headers
    )
    assert res.status_code == 200
    for b in res.json()["broadcasts"]:
        assert b["status"] == "sent"


def test_list_broadcasts_search(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    wa_id, em_id = _seed_one_of_each()
    res = client.get(
        "/api/v2/broadcasts?search=B6-test", headers=auth_headers
    )
    assert res.status_code == 200
    ids = {b["id"] for b in res.json()["broadcasts"]}
    # Both seeded rows have "B6-test" in their names
    assert f"wa-{wa_id}" in ids
    assert f"em-{em_id}" in ids


def test_list_broadcasts_pagination(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    _seed_one_of_each()
    _seed_one_of_each()
    res = client.get(
        "/api/v2/broadcasts?page=0&page_size=1", headers=auth_headers
    )
    body = res.json()
    assert len(body["broadcasts"]) == 1
    assert body["page_size"] == 1
    assert body["total_pages"] >= 2


def test_list_broadcasts_invalid_channel_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get(
        "/api/v2/broadcasts?channel=carrier-pigeon", headers=auth_headers
    )
    assert res.status_code == 400


def test_list_broadcasts_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v2/broadcasts").status_code == 401


# ─── Phase 3.1 Compose endpoints ─────────────────────────────────────────


def test_audience_preview_returns_funnel(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Audience preview returns the 5-counter funnel + breakdown buckets
    (B3 fix data source). 'all_opted_in' is v1's universal segment."""
    res = client.post(
        "/api/v2/broadcasts/audience-preview",
        json={
            "channel": "email",
            "filters": {"segment_id": "all_opted_in"},
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    for key in (
        "total_in_segment",
        "eligible_on_channel",
        "final_recipients",
        "excluded_by_channel",
        "excluded_by_filters",
    ):
        assert key in body
    # total >= eligible >= final by construction
    assert body["total_in_segment"] >= body["eligible_on_channel"]
    assert body["eligible_on_channel"] >= body["final_recipients"]
    # Breakdown shape
    for bucket in ("consent", "geography", "lifecycle", "customer_type"):
        assert isinstance(body[bucket], list)


def test_cost_estimate_returns_total(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Cost estimate returns recipients + per-message + total displays."""
    res = client.post(
        "/api/v2/broadcasts/cost-estimate",
        json={
            "channel": "whatsapp",
            "category": "marketing",
            "filters": {"segment_id": "all_opted_in"},
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "recipients" in body
    assert "per_message_display" in body
    assert "total_display" in body
    assert isinstance(body["breakdown"], list)


def test_send_wa_validates_required_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Empty name → 400 before any DB write or Meta call."""
    res = client.post(
        "/api/v2/broadcasts/wa",
        json={
            "name": "  ",
            "template_id": "welcome_message",
            "filters": {"segment_id": "all_opted_in"},
        },
        headers=auth_headers,
    )
    assert res.status_code == 400


# ─── Phase 3.1b.1 — Email queue + jobs ───────────────────────────────────


def test_queue_email_broadcast_returns_job_id(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /broadcasts/email returns 202 + job_id immediately and
    the background task transitions the job to done (or failed)."""
    # Stub send_broadcast so the test doesn't actually attempt SMTP.
    from services.broadcast_engine import BroadcastResult  # type: ignore[import-not-found]
    from api_v2.routers import broadcasts as broadcasts_router

    def _stub(db, name, channel, template_id, filters, subject=""):  # noqa: ANN001
        return BroadcastResult(
            broadcast_id=999, sent=2, failed=0, total=2, errors=[],
        )

    monkeypatch.setattr(broadcasts_router, "send_broadcast", _stub)

    res = client.post(
        "/api/v2/broadcasts/email",
        json={
            "name": "Phase 3.1b.1 test",
            "template_id": "b2b_introduction",
            "filters": {"segment_id": "all_opted_in"},
        },
        headers=auth_headers,
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert "job_id" in body
    assert "estimated_recipients" in body

    # TestClient runs background tasks synchronously after the response,
    # so the job is already terminal by the time we poll.
    status_res = client.get(
        f"/api/v2/jobs/{body['job_id']}/status", headers=auth_headers,
    )
    assert status_res.status_code == 200
    state = status_res.json()
    assert state["status"] in {"done", "failed"}
    assert state["progress"] == 100 or state["status"] == "failed"


def test_queue_email_broadcast_rejects_missing_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.post(
        "/api/v2/broadcasts/email",
        json={"name": "  ", "template_id": "x"},
        headers=auth_headers,
    )
    assert res.status_code == 400


def test_get_job_status_unknown_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get(
        "/api/v2/jobs/00000000-0000-0000-0000-000000000000/status",
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_jobs_endpoint_requires_auth(client: TestClient) -> None:
    assert (
        client.get("/api/v2/jobs/whatever/status").status_code == 401
    )


# ─── Phase 3.1b.3 — Detail + recipient pagination ────────────────────────


def test_get_broadcast_email(client: TestClient, auth_headers: dict[str, str]) -> None:
    _wa_id, em_id = _seed_one_of_each()
    res = client.get(f"/api/v2/broadcasts/em-{em_id}", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == f"em-{em_id}"
    assert body["channel"] == "email"


def test_get_broadcast_invalid_prefix_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get("/api/v2/broadcasts/xx-1", headers=auth_headers)
    assert res.status_code == 400


def test_get_broadcast_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    res = client.get("/api/v2/broadcasts/em-9999999", headers=auth_headers)
    assert res.status_code == 404


def test_recipients_pagination_email(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Cursor pagination on EmailSend rows scoped to a campaign.
    B16 fix: no silent 100-row cap; page_size + cursor is the contract."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import (  # type: ignore[import-not-found]
        Campaign,
        EmailSend,
    )

    _wa_id, em_id = _seed_one_of_each()
    # Insert 7 EmailSend rows for that campaign.
    db = get_db()
    try:
        for i in range(7):
            db.add(
                EmailSend(
                    contact_id=f"recip_{em_id}_{i}",
                    contact_email=f"to+{i}@example.com",
                    campaign_id=em_id,
                    subject="hi",
                    status="sent",
                    sent_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
    finally:
        db.close()

    page1 = client.get(
        f"/api/v2/broadcasts/em-{em_id}/recipients?page_size=3",
        headers=auth_headers,
    ).json()
    assert page1["total"] == 7
    assert len(page1["recipients"]) == 3
    assert page1["next_cursor"] is not None

    page2 = client.get(
        f"/api/v2/broadcasts/em-{em_id}/recipients?page_size=3&cursor={page1['next_cursor']}",
        headers=auth_headers,
    ).json()
    assert len(page2["recipients"]) == 3
    assert page2["next_cursor"] is not None
    # No overlap between pages
    page1_ids = {r["id"] for r in page1["recipients"]}
    page2_ids = {r["id"] for r in page2["recipients"]}
    assert page1_ids.isdisjoint(page2_ids)

    page3 = client.get(
        f"/api/v2/broadcasts/em-{em_id}/recipients?page_size=3&cursor={page2['next_cursor']}",
        headers=auth_headers,
    ).json()
    assert len(page3["recipients"]) == 1
    assert page3["next_cursor"] is None  # end


def test_recipients_status_filter(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import EmailSend  # type: ignore[import-not-found]

    _wa_id, em_id = _seed_one_of_each()
    db = get_db()
    try:
        db.add_all([
            EmailSend(contact_id=f"f_{em_id}", contact_email="f@x.com",
                      campaign_id=em_id, status="failed",
                      error_message="bounce"),
            EmailSend(contact_id=f"s_{em_id}", contact_email="s@x.com",
                      campaign_id=em_id, status="sent",
                      sent_at=datetime.now(timezone.utc)),
        ])
        db.commit()
    finally:
        db.close()

    failed = client.get(
        f"/api/v2/broadcasts/em-{em_id}/recipients?status=failed",
        headers=auth_headers,
    ).json()
    assert all(r["status"] == "failed" for r in failed["recipients"])
    assert any(r["error_message"] == "bounce" for r in failed["recipients"])


def test_recipients_require_auth(client: TestClient) -> None:
    assert client.get("/api/v2/broadcasts/em-1/recipients").status_code == 401


def test_compose_endpoints_require_auth(client: TestClient) -> None:
    assert (
        client.post("/api/v2/broadcasts/audience-preview", json={"channel": "email"}).status_code
        == 401
    )
    assert (
        client.post("/api/v2/broadcasts/cost-estimate", json={"channel": "email"}).status_code
        == 401
    )
    assert (
        client.post("/api/v2/broadcasts/wa", json={"name": "x", "template_id": "y"}).status_code
        == 401
    )
