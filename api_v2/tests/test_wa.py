"""Smoke tests for /api/v2/wa/* (Phase 2.0 read endpoints)."""

from __future__ import annotations

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


def _seed_wa(window_open: bool = True) -> tuple[str, int]:
    """Seed one Contact + one WAChat + two WAMessages.

    Returns (contact_id, chat_id). `window_open=True` sets
    window_expires_at 6h in the future; False sets it 6h in the past.
    """
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import (  # type: ignore[import-not-found]
        Contact,
        WAChat,
        WAMessage,
    )

    db = get_db()
    try:
        cid = "wa_test_contact_1"
        if not db.query(Contact).filter(Contact.id == cid).first():
            db.add(
                Contact(
                    id=cid,
                    first_name="Inbox",
                    last_name="Tester",
                    company="Acme WA Co",
                    phone="9988776655",
                    wa_id="919988776655",
                    consent_status="opted_in",
                    lifecycle="customer",
                    country="India",
                )
            )

        chat = db.query(WAChat).filter(WAChat.contact_id == cid).first()
        delta = timedelta(hours=6 if window_open else -6)
        if chat is None:
            chat = WAChat(
                contact_id=cid,
                last_message_at=datetime.now(timezone.utc),
                last_message_preview="Test inbound",
                unread_count=1,
                window_expires_at=datetime.now(timezone.utc) + delta,
            )
            db.add(chat)
            db.flush()  # populate chat.id
        else:
            chat.window_expires_at = datetime.now(timezone.utc) + delta
            chat.last_message_preview = "Test inbound"

        if not db.query(WAMessage).filter(WAMessage.contact_id == cid).first():
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
    item = next(c for c in body["conversations"] if c["contact_id"] == cid)
    assert item["contact_name"] == "Inbox Tester"
    assert item["contact_company"] == "Acme WA Co"
    assert item["window_open"] is True
    assert item["unread_count"] >= 1


def test_list_conversations_search(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    _seed_wa()
    res = client.get(
        "/api/v2/wa/conversations?search=acme",
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    for c in body["conversations"]:
        assert "acme" in c["contact_company"].lower() or "acme" in c["contact_name"].lower()


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
    assert len(body["messages"]) >= 2
    directions = {m["direction"] for m in body["messages"]}
    assert directions == {"in", "out"}


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


def test_list_templates_default_approved_only(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Default returns only APPROVED, non-draft templates."""
    res = client.get("/api/v2/wa/templates", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    for t in body["templates"]:
        assert t["status"] == "APPROVED"
        # variables key is always present (possibly empty list)
        assert isinstance(t["variables"], list)


def test_list_templates_extracts_variables(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Inserted template with body referencing {{1}} and {{name}} returns
    them in first-appearance order."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WATemplate  # type: ignore[import-not-found]

    db = get_db()
    try:
        t = WATemplate(
            name="phase2_var_test",
            language="en_US",
            category="MARKETING",
            status="APPROVED",
            body_text="Hi {{name}}, your order {{1}} is ready.",
            header_text=None,
            buttons=[],
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
    body = res.json()
    target = next((t for t in body["templates"] if t["name"] == "phase2_var_test"), None)
    assert target is not None
    assert target["variables"] == ["name", "1"]
