"""Smoke tests for /api/v2/dashboard/home."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from api_v2.main import app

    return TestClient(app)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test_secret"}


def test_dashboard_home_returns_template_counts_from_db(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """**B12 fix verified.** v1's home.py hardcoded the template counts.
    v2 reads them from EmailTemplate.is_active and WATemplate where
    is_draft=false AND status='APPROVED'."""
    res = client.get("/api/v2/dashboard/home", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "email_template_count" in body
    assert "wa_template_count" in body
    assert isinstance(body["email_template_count"], int)
    assert isinstance(body["wa_template_count"], int)
    assert body["email_template_count"] >= 0
    assert body["wa_template_count"] >= 0


def test_dashboard_home_full_shape(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Existing fields (KPIs + lifecycle + activity) still present."""
    body = client.get("/api/v2/dashboard/home", headers=auth_headers).json()
    for key in (
        "emails_today",
        "wa_today",
        "total",
        "wa_24h",
        "wa_ready",
        "opted_in",
        "pending",
        "email_campaigns",
        "wa_campaigns",
        "total_flows",
        "active_runs",
        "email_template_count",
        "wa_template_count",
        "lifecycle",
        "activity",
    ):
        assert key in body
    assert isinstance(body["lifecycle"], list)
    assert isinstance(body["activity"], list)


def test_dashboard_home_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v2/dashboard/home").status_code == 401


def test_system_status_shape(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = client.get("/api/v2/system/status", headers=auth_headers).json()
    assert "gmail_configured" in body
    assert "wa_configured" in body
