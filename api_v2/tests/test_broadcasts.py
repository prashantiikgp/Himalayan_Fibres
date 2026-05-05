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
