"""Smoke tests for /api/v2/wa/* (Phase 2.0 read endpoints)."""

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


def _seed_wa(window_open: bool = True, archived: bool = False) -> tuple[str, int]:
    """Seed one Contact + one WAChat + two WAMessages with a unique
    contact_id per call so tests don't share state across runs.
    Review fix #9 (pre-existing fix; reapplied here).
    """
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import (  # type: ignore[import-not-found]
        Contact,
        WAChat,
        WAMessage,
    )

    stamp = int(time.time() * 1000)
    cid = f"wa_test_{stamp}"
    db = get_db()
    try:
        db.add(
            Contact(
                id=cid,
                first_name="Inbox",
                last_name="Tester",
                company=f"Acme WA Co {stamp % 1000}",
                phone=f"998877{stamp % 10000:04d}",
                wa_id=f"91998877{stamp % 10000:04d}",
                consent_status="opted_in",
                lifecycle="customer",
                country="India",
            )
        )
        delta = timedelta(hours=6 if window_open else -6)
        chat = WAChat(
            contact_id=cid,
            last_message_at=datetime.now(timezone.utc),
            last_message_preview="Test inbound",
            unread_count=1,
            is_archived=archived,
            window_expires_at=datetime.now(timezone.utc) + delta,
        )
        db.add(chat)
        db.flush()  # populate chat.id

        db.add_all(
            [
                WAMessage(
                    chat_id=chat.id,
                    contact_id=cid,
                    direction="in",
                    status="delivered",
                    text="Hi, looking for samples.",
                    created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
                ),
                WAMessage(
                    chat_id=chat.id,
                    contact_id=cid,
                    direction="out",
                    status="sent",
                    text="Sure — sending now.",
                    created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                ),
            ]
        )
        db.commit()
        return cid, chat.id
    finally:
        db.close()


def test_list_conversations(client: TestClient, auth_headers: dict[str, str]) -> None:
    cid, _ = _seed_wa(window_open=True)
    res = client.get("/api/v2/wa/conversations", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] >= 1
    assert "page" in body and "page_size" in body and "total_pages" in body
    item = next(c for c in body["conversations"] if c["contact_id"] == cid)
    assert item["contact_name"] == "Inbox Tester"
    assert item["window_open"] is True
    assert item["unread_count"] >= 1


def test_list_conversations_search_sql(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """SQL-side ILIKE search filters by company case-insensitively
    (review fix #1 — was Python-side filtering before)."""
    cid, _ = _seed_wa()
    # Look up the seeded company name to use a substring of it
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import Contact  # type: ignore[import-not-found]

    db = get_db()
    try:
        company = db.query(Contact).filter(Contact.id == cid).one().company
    finally:
        db.close()

    # First word of the company name (e.g. "Acme") will be present case-insensitively
    needle = company.split()[0].lower()
    res = client.get(
        f"/api/v2/wa/conversations?search={needle}", headers=auth_headers
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert any(c["contact_id"] == cid for c in body["conversations"])
    # Every returned row should match the needle case-insensitively
    for c in body["conversations"]:
        haystack = f"{c['contact_name']} {c['contact_company']}".lower()
        assert needle in haystack


def test_list_conversations_pagination(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """page_size=1 paginates one row at a time (review fix #2)."""
    _seed_wa()
    _seed_wa()
    res = client.get(
        "/api/v2/wa/conversations?page=0&page_size=1", headers=auth_headers
    )
    body = res.json()
    assert len(body["conversations"]) == 1
    assert body["page_size"] == 1
    assert body["total_pages"] >= 2

    # Page beyond total clamps to last page (matches contacts router).
    res2 = client.get(
        "/api/v2/wa/conversations?page=999&page_size=1", headers=auth_headers
    )
    assert res2.status_code == 200
    assert res2.json()["page"] < res2.json()["total_pages"]


def test_list_conversations_archived(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """archived=true filter returns archived chats (review fix #14)."""
    cid_archived, _ = _seed_wa(archived=True)
    cid_active, _ = _seed_wa(archived=False)
    archived = client.get(
        "/api/v2/wa/conversations?archived=true", headers=auth_headers
    ).json()
    assert any(c["contact_id"] == cid_archived for c in archived["conversations"])
    assert all(c["contact_id"] != cid_active for c in archived["conversations"])

    active = client.get("/api/v2/wa/conversations", headers=auth_headers).json()
    assert any(c["contact_id"] == cid_active for c in active["conversations"])
    assert all(c["contact_id"] != cid_archived for c in active["conversations"])


def test_list_conversations_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v2/wa/conversations").status_code == 401


def test_get_conversation_detail(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    cid, _ = _seed_wa(window_open=True)
    res = client.get(f"/api/v2/wa/conversations/{cid}", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["contact_id"] == cid
    assert body["contact_name"] == "Inbox Tester"
    assert body["window_open"] is True
    assert body["last_inbound_at"] is not None
    assert len(body["messages"]) == 2
    assert {m["direction"] for m in body["messages"]} == {"in", "out"}


def test_get_conversation_message_limit(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """`?limit=N` caps + returns the most recent N messages chronologically
    (review fix #4)."""
    cid, _ = _seed_wa()
    res = client.get(
        f"/api/v2/wa/conversations/{cid}?limit=1", headers=auth_headers
    )
    body = res.json()
    assert len(body["messages"]) == 1
    # Newest message returned should be the most recent (the "out" one,
    # since seed creates the inbound 10 min ago and outbound 5 min ago).
    assert body["messages"][0]["direction"] == "out"


def test_get_conversation_window_closed(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A chat whose window has expired returns window_open=false — the
    frontend uses this to disable the text composer (B2 fix)."""
    cid, _ = _seed_wa(window_open=False)
    res = client.get(f"/api/v2/wa/conversations/{cid}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["window_open"] is False


def test_get_conversation_unknown_contact(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get(
        "/api/v2/wa/conversations/nonexistent_xxx", headers=auth_headers
    )
    assert res.status_code == 404


def test_legacy_direction_values_normalized(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A WAMessage row with direction='incoming' or 'outgoing' (legacy
    DB values) should be normalized to in/out by the schema validator
    (review fix #5)."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import (  # type: ignore[import-not-found]
        Contact,
        WAChat,
        WAMessage,
    )

    stamp = int(time.time() * 1000)
    cid = f"wa_legacy_{stamp}"
    db = get_db()
    try:
        db.add(
            Contact(
                id=cid,
                first_name="Legacy",
                last_name="Direction",
                phone=f"977700{stamp % 10000:04d}",
                wa_id=f"91977700{stamp % 10000:04d}",
                country="India",
            )
        )
        chat = WAChat(
            contact_id=cid,
            last_message_at=datetime.now(timezone.utc),
            last_message_preview="legacy",
            window_expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )
        db.add(chat)
        db.flush()
        db.add_all(
            [
                WAMessage(
                    chat_id=chat.id, contact_id=cid, direction="incoming",
                    status="delivered", text="legacy in",
                    created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
                ),
                WAMessage(
                    chat_id=chat.id, contact_id=cid, direction="outgoing",
                    status="sent", text="legacy out",
                    created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    res = client.get(f"/api/v2/wa/conversations/{cid}", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert {m["direction"] for m in body["messages"]} == {"in", "out"}
    # last_inbound_at must still be detected even though raw was "incoming"
    assert body["last_inbound_at"] is not None


def test_list_templates_default_approved_only(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get("/api/v2/wa/templates", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    for t in body["templates"]:
        assert t["status"] == "APPROVED"
        assert isinstance(t["variables"], list)


def test_list_templates_extracts_variables(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Inserted template with body+footer+button vars returns the deduped
    set in first-appearance order (review fix #3 + #11)."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WATemplate  # type: ignore[import-not-found]

    stamp = int(time.time() * 1000)
    name = f"phase2_var_test_{stamp}"
    db = get_db()
    try:
        t = WATemplate(
            name=name,
            language="en_US",
            category="MARKETING",
            status="APPROVED",
            # `{{ name }}` (whitespace tolerated), `{{1}}`, repeat `{{name}}`
            # in footer, and a button URL with another placeholder.
            body_text="Hi {{ name }}, your order {{1}} is ready. {{name}} again.",
            header_text=None,
            footer_text="Thanks {{name}} — see you at {{shop}}",
            buttons=[{"type": "URL", "text": "Track", "url": "https://x.com/{{1}}"}],
            variables=[],
            is_draft=False,
        )
        db.add(t)
        db.commit()
    finally:
        db.close()

    res = client.get(
        "/api/v2/wa/templates?status=APPROVED", headers=auth_headers
    )
    target = next(t for t in res.json()["templates"] if t["name"] == name)
    # Order: name (body) -> 1 (body) -> shop (footer). Duplicates deduped.
    assert target["variables"] == ["name", "1", "shop"]
