"""Smoke tests for /api/v2/contacts (review fix M2)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HF_DASHBOARD = _REPO_ROOT / "hf_dashboard"
if _HF_DASHBOARD.exists() and str(_HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_HF_DASHBOARD))

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_HF_DASHBOARD / 'data' / 'test_contacts.db'}")
os.environ.setdefault("APP_PASSWORD", "test_secret")


@pytest.fixture()
def client() -> TestClient:
    from api_v2.main import app

    return TestClient(app)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test_secret"}


def _seed_contacts(n: int = 5) -> list[str]:
    """Insert N test contacts with varied lifecycles + segments. Returns IDs."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import Contact  # type: ignore[import-not-found]

    db = get_db()
    try:
        ids: list[str] = []
        for i in range(n):
            cid = f"test_contact_{i}"
            existing = db.query(Contact).filter(Contact.id == cid).first()
            if existing:
                ids.append(cid)
                continue
            db.add(
                Contact(
                    id=cid,
                    first_name=f"First{i}",
                    last_name=f"Last{i}",
                    email=f"test{i}@example.com",
                    company=f"Company {i}",
                    phone=f"+91900000000{i}",
                    wa_id=f"91900000000{i}",
                    lifecycle="customer" if i % 2 == 0 else "new_lead",
                    customer_type="domestic_b2b",
                    consent_status="opted_in" if i % 2 == 0 else "pending",
                    country="India",
                    tags=["test", f"batch_{i % 2}"],
                )
            )
            ids.append(cid)
        db.commit()
        return ids
    finally:
        db.close()


def test_contacts_list_paginated(client: TestClient, auth_headers: dict[str, str]) -> None:
    _seed_contacts(5)
    res = client.get("/api/v2/contacts?page_size=2&page=0", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert len(body["contacts"]) == 2
    assert body["page_size"] == 2
    assert body["total"] >= 5
    assert body["total_pages"] >= 3


def test_contacts_list_requires_auth(client: TestClient) -> None:
    """No Authorization header → 401 (verifies M1 fail-closed enforcement)."""
    res = client.get("/api/v2/contacts?page_size=2")
    assert res.status_code == 401


def test_contacts_filter_by_lifecycle(client: TestClient, auth_headers: dict[str, str]) -> None:
    _seed_contacts(5)
    res = client.get(
        "/api/v2/contacts?lifecycle=customer&page_size=200", headers=auth_headers
    )
    assert res.status_code == 200
    body = res.json()
    for c in body["contacts"]:
        assert c["lifecycle"] == "customer"


def test_contacts_filter_by_channel_email(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    _seed_contacts(5)
    res = client.get(
        "/api/v2/contacts?channel=email&page_size=200", headers=auth_headers
    )
    assert res.status_code == 200
    body = res.json()
    for c in body["contacts"]:
        assert c["email"]
        assert "email" in c["channels"]


def test_contacts_search_by_name(client: TestClient, auth_headers: dict[str, str]) -> None:
    _seed_contacts(5)
    res = client.get(
        "/api/v2/contacts?search=First1&page_size=200", headers=auth_headers
    )
    assert res.status_code == 200
    body = res.json()
    # Either matches our test contact or a real contact with First1 in name —
    # the assertion is that the filter narrowed the result set.
    assert body["total"] >= 1
    assert any("First1" in c["first_name"] or "First1" in (c["last_name"] or "") for c in body["contacts"])


def test_segments_endpoint(client: TestClient, auth_headers: dict[str, str]) -> None:
    res = client.get("/api/v2/segments", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["segments"], list)
    # Real DB has segments seeded; if empty in test env, the structure is still valid.
    for s in body["segments"]:
        assert "id" in s
        assert "name" in s
        assert "member_count" in s


def test_contacts_no_results_returns_empty_list(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get(
        "/api/v2/contacts?search=zzzzz_nonexistent_xyz_nope", headers=auth_headers
    )
    assert res.status_code == 200
    body = res.json()
    assert body["contacts"] == []
    assert body["total"] == 0


def test_contacts_pagination_clamps_high_page(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Asking for an out-of-range page returns the last available page (Mn3)."""
    res = client.get("/api/v2/contacts?page=9999&page_size=50", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    # Page is clamped to total_pages - 1 (or 0 if no rows)
    assert body["page"] < body["total_pages"]
