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


def test_contacts_filter_by_segment_evaluates_rules(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """**Phase 6.1 fix.** Selecting a segment must evaluate its rules,
    not compare segment_id against customer_type. Previously every
    segment returned 0 because the comparison never matched."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import Contact, Segment  # type: ignore[import-not-found]

    import uuid
    seg_id = uuid.uuid4().hex[:8]
    cid = f"phase6_seg_{seg_id}"

    db = get_db()
    try:
        if not db.query(Contact).filter(Contact.id == cid).first():
            db.add(
                Contact(
                    id=cid,
                    first_name="Segment",
                    last_name="Test",
                    customer_type="phase6_test_type",
                    consent_status="opted_in",
                    country="India",
                )
            )
        if db.query(Segment).filter(Segment.id == seg_id).first() is None:
            db.add(
                Segment(
                    id=seg_id,
                    name=f"Phase 6 segment {seg_id}",
                    rules={"customer_type": ["phase6_test_type"]},
                    is_active=True,
                )
            )
        db.commit()
    finally:
        db.close()

    res = client.get(
        f"/api/v2/contacts?segment={seg_id}&page_size=200",
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] >= 1
    assert any(c["id"] == cid for c in body["contacts"])


def test_contacts_filter_by_unknown_segment_returns_empty(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Unknown segment id → empty result, not 500."""
    res = client.get(
        "/api/v2/contacts?segment=nonexistent_xyz",
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["contacts"] == []
    assert res.json()["total"] == 0


def test_contacts_pagination_clamps_high_page(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Asking for an out-of-range page returns the last available page (Mn3)."""
    res = client.get("/api/v2/contacts?page=9999&page_size=50", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    # Page is clamped to total_pages - 1 (or 0 if no rows)
    assert body["page"] < body["total_pages"]


# ─── Write-endpoint tests (review fix Mn-new-2) ──────────────────────────


def test_create_contact_minimal(client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST /contacts with required fields returns 201 + the created row."""
    import time

    stamp = int(time.time() * 1000)
    unique = f"create_test_{stamp}@example.com"
    phone = f"998877{stamp % 10000:04d}"
    res = client.post(
        "/api/v2/contacts",
        json={"first_name": "CreateTest", "phone": phone, "email": unique},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["first_name"] == "CreateTest"
    assert body["wa_id"] == f"91{phone}"
    assert "email" in body["channels"]


def test_create_contact_short_phone_400(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Phone with <10 digits is rejected (review fix Mn-new-3 mirror)."""
    res = client.post(
        "/api/v2/contacts",
        json={"first_name": "Short", "phone": "123"},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "10 digits" in res.json()["detail"]


def test_create_contact_duplicate_email_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Second POST with the same email returns 409 (M-new-2 IntegrityError handling).

    Uses a unique phone too — wa_id has a UNIQUE constraint, so reusing a
    phone from an earlier test would also collide and skew this assertion.
    """
    import time

    stamp = int(time.time() * 1000)
    email = f"dup_test_{stamp}@example.com"
    phone = f"998877{stamp % 10000:04d}"  # unique 10-digit phone
    body = {"first_name": "Dup", "phone": phone, "email": email}
    first = client.post("/api/v2/contacts", json=body, headers=auth_headers)
    assert first.status_code == 201, first.text
    second = client.post("/api/v2/contacts", json=body, headers=auth_headers)
    assert second.status_code == 409, second.text


def test_update_contact_short_phone_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """PATCH with <10-digit phone is rejected (review fix Mn-new-3)."""
    import time

    stamp = int(time.time() * 1000)
    seed = client.post(
        "/api/v2/contacts",
        json={
            "first_name": "PhoneCheck",
            "phone": f"991122{stamp % 10000:04d}",
            "email": f"phonecheck_{stamp}@example.com",
        },
        headers=auth_headers,
    )
    assert seed.status_code == 201, seed.text
    cid = seed.json()["id"]

    res = client.patch(
        f"/api/v2/contacts/{cid}",
        json={"phone": "5"},
        headers=auth_headers,
    )
    assert res.status_code == 400


def test_update_contact_round_trip(client: TestClient, auth_headers: dict[str, str]) -> None:
    """PATCH applies provided fields and round-trips through GET."""
    import time

    stamp = int(time.time() * 1000)
    seed = client.post(
        "/api/v2/contacts",
        json={
            "first_name": "Edit",
            "phone": f"912345{stamp % 10000:04d}",
            "email": f"edit_{stamp}@example.com",
        },
        headers=auth_headers,
    )
    assert seed.status_code == 201, seed.text
    cid = seed.json()["id"]

    upd = client.patch(
        f"/api/v2/contacts/{cid}",
        json={"company": "Edited Co", "consent_status": "opted_in"},
        headers=auth_headers,
    )
    assert upd.status_code == 200
    body = upd.json()
    assert body["company"] == "Edited Co"
    assert body["consent_status"] == "opted_in"

    detail = client.get(f"/api/v2/contacts/{cid}", headers=auth_headers)
    assert detail.json()["company"] == "Edited Co"


def test_update_contact_404_unknown(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.patch(
        "/api/v2/contacts/does_not_exist",
        json={"first_name": "Ghost"},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_add_note_round_trip(client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST /contacts/{id}/notes appends a threaded note visible via GET."""
    import time

    stamp = int(time.time() * 1000)
    seed = client.post(
        "/api/v2/contacts",
        json={
            "first_name": "NoteSubject",
            "phone": f"955511{stamp % 10000:04d}",
            "email": f"note_{stamp}@example.com",
        },
        headers=auth_headers,
    )
    assert seed.status_code == 201, seed.text
    cid = seed.json()["id"]

    note_res = client.post(
        f"/api/v2/contacts/{cid}/notes",
        json={"body": "First contact made via cold outreach."},
        headers=auth_headers,
    )
    assert note_res.status_code == 201
    assert note_res.json()["body"].startswith("First contact")

    detail = client.get(f"/api/v2/contacts/{cid}", headers=auth_headers).json()
    assert any(n["body"].startswith("First contact") for n in detail["threaded_notes"])


def test_csv_download_streams(client: TestClient, auth_headers: dict[str, str]) -> None:
    """GET /contacts.csv returns CSV with the expected header row."""
    res = client.get("/api/v2/contacts.csv", headers=auth_headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    text = res.text
    first_line = text.splitlines()[0]
    assert first_line == "email,first_name,last_name,company,phone,country,lifecycle,consent_status,wa_id"


def test_import_csv_basic(client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST /contacts/import with a 2-row CSV imports them; duplicates skipped."""
    import time

    stamp = int(time.time() * 1000)
    # Phones must be unique across test runs too — wa_id has a UNIQUE
    # constraint, and re-running the suite without clearing the DB would
    # otherwise hit a 409 on the bulk commit (review fix M-new-2).
    phone_a = f"901111{stamp % 10000:04d}"
    phone_b = f"901112{stamp % 10000:04d}"
    csv_body = (
        "email,first_name,last_name,company,phone,country\n"
        f"importer_a_{stamp}@example.com,Importer,A,Acme A,{phone_a},India\n"
        f"importer_b_{stamp}@example.com,Importer,B,Acme B,{phone_b},India\n"
    )
    res = client.post(
        "/api/v2/contacts/import",
        files={"file": ("test.csv", csv_body.encode(), "text/csv")},
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0

    # Re-uploading the same file → both skipped as duplicates.
    res2 = client.post(
        "/api/v2/contacts/import",
        files={"file": ("test.csv", csv_body.encode(), "text/csv")},
        headers=auth_headers,
    )
    assert res2.status_code == 200
    assert res2.json()["imported"] == 0
    assert res2.json()["skipped"] == 2


def test_import_rejects_non_csv_xlsx(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.post(
        "/api/v2/contacts/import",
        files={"file": ("test.txt", b"hello", "text/plain")},
        headers=auth_headers,
    )
    assert res.status_code == 400


# -- POST /contacts/{id}/lifecycle (B2) --


def test_set_lifecycle_updates_field_and_logs_interaction(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    cid = _seed_contacts(1)[0]
    res = client.post(
        f"/api/v2/contacts/{cid}/lifecycle",
        json={"lifecycle": "interested", "note": "Asked for samples"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["lifecycle"] == "interested"
    # The activity timeline (newest first) should now have the move.
    assert any(
        a["kind"] == "lifecycle_interested"
        and "interested" in a["summary"]
        and "Asked for samples" in a["summary"]
        for a in body["activity"]
    )


def test_set_lifecycle_rejects_unknown_value(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    cid = _seed_contacts(1)[0]
    res = client.post(
        f"/api/v2/contacts/{cid}/lifecycle",
        json={"lifecycle": "not_a_real_state"},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_set_lifecycle_404_on_unknown_contact(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.post(
        "/api/v2/contacts/does_not_exist/lifecycle",
        json={"lifecycle": "interested"},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_set_lifecycle_requires_auth(client: TestClient) -> None:
    res = client.post(
        "/api/v2/contacts/test_contact_0/lifecycle",
        json={"lifecycle": "interested"},
    )
    assert res.status_code == 401


def test_list_contacts_supports_multi_lifecycle_filter(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """B3: ?lifecycle=contacted&lifecycle=interested filters by both."""
    cids = _seed_contacts(4)
    # Move two contacts into the "Needs follow-up" cohort.
    for i, cid in enumerate(cids[:2]):
        target = "contacted" if i == 0 else "interested"
        client.post(
            f"/api/v2/contacts/{cid}/lifecycle",
            json={"lifecycle": target},
            headers=auth_headers,
        )

    res = client.get(
        "/api/v2/contacts?lifecycle=contacted&lifecycle=interested&page_size=200",
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    returned_ids = {c["id"] for c in body["contacts"]}
    # Both moved contacts present, neither of the unchanged contacts.
    assert cids[0] in returned_ids
    assert cids[1] in returned_ids
    for r in body["contacts"]:
        assert r["lifecycle"] in {"contacted", "interested"}
