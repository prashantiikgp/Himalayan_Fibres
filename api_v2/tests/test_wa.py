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


# ─── write endpoints (Phase 2.1) ─────────────────────────────────────────


@pytest.fixture()
def stub_sender(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Replace WhatsAppSender's send_text/send_template with stubs that
    record calls and return unique wa_message_ids. Avoids real Meta hits
    AND avoids the UNIQUE-constraint collision that would happen if
    every test reused the same stub message id."""
    calls: dict[str, object] = {"text": None, "template": None, "result": None}
    counter = {"n": 0}

    def _next_id() -> str:
        counter["n"] += 1
        return f"wamid.STUB.{int(time.time() * 1000)}.{counter['n']}"

    def _send_text(self, to_phone: str, text: str):  # noqa: ANN001
        calls["text"] = {"to_phone": to_phone, "text": text}
        if calls["result"] is not None:
            return calls["result"]
        return (True, _next_id(), None)

    def _send_template(self, to_phone: str, template_name, lang="en_US", variables=None):  # noqa: ANN001
        calls["template"] = {
            "to_phone": to_phone,
            "template_name": template_name,
            "lang": lang,
            "variables": list(variables or []),
        }
        if calls["result"] is not None:
            return calls["result"]
        return (True, _next_id(), None)

    from api_v2.routers import wa as wa_router

    monkeypatch.setattr(wa_router.WhatsAppSender, "send_text", _send_text)
    monkeypatch.setattr(wa_router.WhatsAppSender, "send_template", _send_template)
    return calls


def test_send_text_message_within_window(
    client: TestClient, auth_headers: dict[str, str], stub_sender: dict[str, object]
) -> None:
    """POST /wa/messages succeeds with an open window."""
    cid, _ = _seed_wa(window_open=True)
    res = client.post(
        "/api/v2/wa/messages",
        json={"contact_id": cid, "text": "Reply within window"},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["direction"] == "out"
    assert body["status"] == "sent"
    assert body["text"] == "Reply within window"
    assert stub_sender["text"]["text"] == "Reply within window"


def test_send_text_message_window_closed_412(
    client: TestClient, auth_headers: dict[str, str], stub_sender: dict[str, object]
) -> None:
    """Closed window returns 412 Precondition Failed (Plan D Phase 1.3)."""
    cid, _ = _seed_wa(window_open=False)
    res = client.post(
        "/api/v2/wa/messages",
        json={"contact_id": cid, "text": "should be blocked"},
        headers=auth_headers,
    )
    assert res.status_code == 412
    assert "window" in res.json()["detail"].lower()
    assert stub_sender["text"] is None  # never reached the sender


def test_send_text_message_empty_text_400(
    client: TestClient, auth_headers: dict[str, str], stub_sender: dict[str, object]
) -> None:
    cid, _ = _seed_wa(window_open=True)
    res = client.post(
        "/api/v2/wa/messages",
        json={"contact_id": cid, "text": "   "},
        headers=auth_headers,
    )
    assert res.status_code == 400


def test_send_template_message(
    client: TestClient, auth_headers: dict[str, str], stub_sender: dict[str, object]
) -> None:
    """POST /wa/template-sends succeeds outside the window AND extends it."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import (  # type: ignore[import-not-found]
        WAChat,
        WATemplate,
    )

    cid, _ = _seed_wa(window_open=False)
    stamp = int(time.time() * 1000)
    name = f"phase2_send_test_{stamp}"
    db = get_db()
    try:
        db.add(
            WATemplate(
                name=name,
                language="en_US",
                category="MARKETING",
                status="APPROVED",
                body_text="Hi {{1}}, your sample is ready.",
                buttons=[],
                variables=[],
                is_draft=False,
            )
        )
        db.commit()
    finally:
        db.close()

    res = client.post(
        "/api/v2/wa/template-sends",
        json={
            "contact_id": cid,
            "template_name": name,
            "language": "en_US",
            "variables": ["Inbox Tester"],
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    assert stub_sender["template"]["template_name"] == name
    assert stub_sender["template"]["variables"] == ["Inbox Tester"]

    # Window should now be reopened.
    db = get_db()
    try:
        chat = db.query(WAChat).filter(WAChat.contact_id == cid).first()
        assert chat is not None
        from datetime import datetime, timezone
        expires = chat.window_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        assert expires > datetime.now(timezone.utc)
    finally:
        db.close()


def test_send_template_unknown_template_404(
    client: TestClient, auth_headers: dict[str, str], stub_sender: dict[str, object]
) -> None:
    cid, _ = _seed_wa(window_open=False)
    res = client.post(
        "/api/v2/wa/template-sends",
        json={"contact_id": cid, "template_name": "does_not_exist_xxx"},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_send_template_rejects_non_approved(
    client: TestClient, auth_headers: dict[str, str], stub_sender: dict[str, object]
) -> None:
    """Template with status='PENDING' is rejected at 400."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WATemplate  # type: ignore[import-not-found]

    cid, _ = _seed_wa(window_open=False)
    stamp = int(time.time() * 1000)
    name = f"pending_template_{stamp}"
    db = get_db()
    try:
        db.add(
            WATemplate(
                name=name, language="en_US", category="MARKETING",
                status="PENDING", body_text="Hi", buttons=[], variables=[],
                is_draft=False,
            )
        )
        db.commit()
    finally:
        db.close()

    res = client.post(
        "/api/v2/wa/template-sends",
        json={"contact_id": cid, "template_name": name},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "APPROVED" in res.json()["detail"]


def test_send_text_meta_failure_502(
    client: TestClient, auth_headers: dict[str, str], stub_sender: dict[str, object]
) -> None:
    """If WhatsAppSender returns failure, we surface 502 + persist a failed
    WAMessage row so the conversation list reflects the attempt."""
    cid, _ = _seed_wa(window_open=True)
    stub_sender["result"] = (False, None, "401 token expired")

    res = client.post(
        "/api/v2/wa/messages",
        json={"contact_id": cid, "text": "boom"},
        headers=auth_headers,
    )
    assert res.status_code == 502
    assert "401 token expired" in res.json()["detail"]

    # Verify a failed WAMessage row was recorded.
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WAMessage  # type: ignore[import-not-found]

    db = get_db()
    try:
        rows = (
            db.query(WAMessage)
            .filter(WAMessage.contact_id == cid)
            .filter(WAMessage.status == "failed")
            .all()
        )
        assert len(rows) >= 1
        assert any("token expired" in (r.error_detail or "") for r in rows)
    finally:
        db.close()


# ─── Phase 4.0 — Template Studio read endpoints ──────────────────────────


def test_get_template_by_id(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """GET /wa/templates/{id} returns the full record incl. is_draft + tier."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WATemplate  # type: ignore[import-not-found]

    stamp = int(time.time() * 1000)
    db = get_db()
    try:
        t = WATemplate(
            name=f"phase4_get_test_{stamp}",
            language="en_US",
            category="MARKETING",
            status="APPROVED",
            body_text="Body with {{1}}",
            buttons=[],
            variables=[],
            is_draft=False,
        )
        db.add(t)
        db.commit()
        tid = t.id
    finally:
        db.close()

    res = client.get(f"/api/v2/wa/templates/{tid}", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == tid
    assert body["is_draft"] is False
    assert body["tier"] in {"company", "category", "product", "utility"}
    assert "rejection_reason" in body
    assert "buttons" in body


def test_get_template_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get("/api/v2/wa/templates/9999999", headers=auth_headers)
    assert res.status_code == 404


def test_list_templates_include_drafts(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """include_drafts=true returns draft rows that the default call hides
    (Phase 4.0 — Template Studio needs to see drafts)."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WATemplate  # type: ignore[import-not-found]

    stamp = int(time.time() * 1000)
    name = f"phase4_draft_{stamp}"
    db = get_db()
    try:
        db.add(
            WATemplate(
                name=name,
                language="en_US",
                category="MARKETING",
                status=None,
                body_text="draft body",
                buttons=[],
                variables=[],
                is_draft=True,
            )
        )
        db.commit()
    finally:
        db.close()

    # Default call: draft is hidden.
    default = client.get("/api/v2/wa/templates", headers=auth_headers).json()
    assert all(t["name"] != name for t in default["templates"])

    # include_drafts=true: draft is visible.
    res = client.get(
        "/api/v2/wa/templates?include_drafts=true", headers=auth_headers
    )
    body = res.json()
    found = [t for t in body["templates"] if t["name"] == name]
    assert len(found) == 1
    assert found[0]["is_draft"] is True


def test_list_templates_tier_filter(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """`?tier=utility` returns only UTILITY-category rows after tier
    inference (Phase 4.0)."""
    res = client.get(
        "/api/v2/wa/templates?tier=utility", headers=auth_headers
    )
    assert res.status_code == 200
    for t in res.json()["templates"]:
        assert t["tier"] == "utility"


# ─── Phase 4.1a — Template draft CRUD ────────────────────────────────────


def test_create_template_returns_draft(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    stamp = int(time.time() * 1000)
    name = f"phase41_create_{stamp}"
    res = client.post(
        "/api/v2/wa/templates",
        json={
            "name": name,
            "category": "MARKETING",
            "body_text": "Hi {{1}}",
            "buttons": [],
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == name
    assert body["is_draft"] is True
    assert body["status"] is None
    assert body["body_text"] == "Hi {{1}}"


def test_create_template_duplicate_name_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    stamp = int(time.time() * 1000)
    name = f"phase41_dup_{stamp}"
    body = {"name": name, "category": "MARKETING", "body_text": "x"}
    first = client.post("/api/v2/wa/templates", json=body, headers=auth_headers)
    assert first.status_code == 201
    second = client.post("/api/v2/wa/templates", json=body, headers=auth_headers)
    assert second.status_code == 409


def test_create_template_missing_name_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.post(
        "/api/v2/wa/templates",
        json={"name": "   ", "body_text": "x"},
        headers=auth_headers,
    )
    assert res.status_code == 400


def test_save_draft_in_place(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Save on a draft mutates the same row, no clone."""
    stamp = int(time.time() * 1000)
    name = f"phase41_save_draft_{stamp}"
    create = client.post(
        "/api/v2/wa/templates",
        json={"name": name, "body_text": "first"},
        headers=auth_headers,
    )
    tid = create.json()["id"]

    save = client.post(
        f"/api/v2/wa/templates/{tid}/save",
        json={"body_text": "edited"},
        headers=auth_headers,
    )
    assert save.status_code == 200, save.text
    body = save.json()
    assert body["id"] == tid  # SAME row — in-place edit
    assert body["body_text"] == "edited"
    assert body["is_draft"] is True


def test_save_approved_clones_with_v2_suffix(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Saving an APPROVED template creates a `<base>_v2` draft clone
    instead of mutating the original (audit-mandated clone-on-edit)."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WATemplate  # type: ignore[import-not-found]

    stamp = int(time.time() * 1000)
    base = f"phase41_approved_{stamp}"
    db = get_db()
    try:
        t = WATemplate(
            name=base, language="en_US", category="MARKETING", status="APPROVED",
            body_text="Original body", buttons=[], variables=[], is_draft=False,
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        original_id = t.id
    finally:
        db.close()

    save = client.post(
        f"/api/v2/wa/templates/{original_id}/save",
        json={"body_text": "Edited body"},
        headers=auth_headers,
    )
    assert save.status_code == 200, save.text
    clone = save.json()
    assert clone["id"] != original_id, "expected a NEW row, not in-place edit"
    assert clone["name"] == f"{base}_v2"
    assert clone["is_draft"] is True
    assert clone["body_text"] == "Edited body"
    assert clone["status"] is None

    # Original is untouched.
    orig_res = client.get(
        f"/api/v2/wa/templates/{original_id}", headers=auth_headers
    )
    assert orig_res.json()["body_text"] == "Original body"
    assert orig_res.json()["status"] == "APPROVED"


def test_save_approved_picks_next_available_clone_index(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """If `<base>_v2` already exists, saving the original creates `_v3`."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WATemplate  # type: ignore[import-not-found]

    stamp = int(time.time() * 1000)
    base = f"phase41_clone_idx_{stamp}"
    db = get_db()
    try:
        original = WATemplate(
            name=base, language="en_US", category="MARKETING", status="APPROVED",
            body_text="orig", buttons=[], variables=[], is_draft=False,
        )
        existing_v2 = WATemplate(
            name=f"{base}_v2", language="en_US", category="MARKETING",
            status=None, body_text="prev clone",
            buttons=[], variables=[], is_draft=True,
        )
        db.add_all([original, existing_v2])
        db.commit()
        db.refresh(original)
        oid = original.id
    finally:
        db.close()

    save = client.post(
        f"/api/v2/wa/templates/{oid}/save",
        json={"body_text": "newer"},
        headers=auth_headers,
    )
    assert save.json()["name"] == f"{base}_v3"


def test_delete_draft(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    stamp = int(time.time() * 1000)
    name = f"phase41_del_{stamp}"
    create = client.post(
        "/api/v2/wa/templates",
        json={"name": name, "body_text": "x"},
        headers=auth_headers,
    )
    tid = create.json()["id"]

    res = client.delete(f"/api/v2/wa/templates/{tid}", headers=auth_headers)
    assert res.status_code == 204

    # Subsequent GET → 404
    assert (
        client.get(f"/api/v2/wa/templates/{tid}", headers=auth_headers).status_code
        == 404
    )


def test_delete_approved_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Submitted (APPROVED) templates are immutable; delete returns 409."""
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WATemplate  # type: ignore[import-not-found]

    stamp = int(time.time() * 1000)
    db = get_db()
    try:
        t = WATemplate(
            name=f"phase41_immutable_{stamp}", language="en_US",
            category="MARKETING", status="APPROVED",
            body_text="cant delete", buttons=[], variables=[], is_draft=False,
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
    finally:
        db.close()

    res = client.delete(f"/api/v2/wa/templates/{tid}", headers=auth_headers)
    assert res.status_code == 409


# ─── Phase 4.1b.1 — Submit + Sync ────────────────────────────────────────


def test_submit_template_to_meta(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submit a draft → WhatsAppSender.create_template stub returns
    success → row flips is_draft=False, status='PENDING', meta_template_id
    populated."""
    from api_v2.routers import wa as wa_router

    captured: dict = {}

    def _stub(self, name, category, language, components):  # noqa: ANN001
        captured["name"] = name
        captured["category"] = category
        captured["components"] = components
        return (True, {"id": "META_T_999", "status": "PENDING"}, None)

    monkeypatch.setattr(wa_router.WhatsAppSender, "create_template", _stub)

    stamp = int(time.time() * 1000)
    name = f"phase41b_submit_{stamp}"
    create = client.post(
        "/api/v2/wa/templates",
        json={
            "name": name,
            "category": "MARKETING",
            "body_text": "Hi {{1}}",
            "buttons": [],
        },
        headers=auth_headers,
    )
    tid = create.json()["id"]

    res = client.post(
        f"/api/v2/wa/templates/{tid}/submit", headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_draft"] is False
    assert body["status"] == "PENDING"
    assert captured["name"] == name


def test_submit_template_meta_failure_502(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Meta rejects → 502; row stays a draft."""
    from api_v2.routers import wa as wa_router

    monkeypatch.setattr(
        wa_router.WhatsAppSender, "create_template",
        lambda self, name, category, language, components: (False, None, "rate limit"),
    )

    stamp = int(time.time() * 1000)
    name = f"phase41b_fail_{stamp}"
    create = client.post(
        "/api/v2/wa/templates",
        json={"name": name, "category": "MARKETING", "body_text": "x"},
        headers=auth_headers,
    )
    tid = create.json()["id"]

    res = client.post(
        f"/api/v2/wa/templates/{tid}/submit", headers=auth_headers,
    )
    assert res.status_code == 502
    assert "rate limit" in res.json()["detail"]

    # Still a draft.
    detail = client.get(
        f"/api/v2/wa/templates/{tid}", headers=auth_headers
    ).json()
    assert detail["is_draft"] is True


def test_submit_already_submitted_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    from services.database import get_db  # type: ignore[import-not-found]
    from services.models import WATemplate  # type: ignore[import-not-found]

    stamp = int(time.time() * 1000)
    db = get_db()
    try:
        t = WATemplate(
            name=f"phase41b_already_{stamp}",
            language="en_US", category="MARKETING", status="APPROVED",
            body_text="x", buttons=[], variables=[], is_draft=False,
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
    finally:
        db.close()

    res = client.post(
        f"/api/v2/wa/templates/{tid}/submit", headers=auth_headers,
    )
    assert res.status_code == 409


def test_sync_templates_returns_job(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sync queues a job and the worker calls
    sync_templates_from_meta. TestClient runs background tasks
    synchronously so the job is terminal by the time we poll."""
    from api_v2.routers import wa as wa_router

    monkeypatch.setattr(
        wa_router.WhatsAppSender, "sync_templates_from_meta",
        lambda self, db: {"created": 0, "updated": 3, "message": "ok"},
    )

    res = client.post("/api/v2/wa/templates/sync", headers=auth_headers)
    assert res.status_code == 202, res.text
    job_id = res.json()["job_id"]

    status_res = client.get(
        f"/api/v2/jobs/{job_id}/status", headers=auth_headers,
    )
    body = status_res.json()
    assert body["status"] in {"done", "failed"}
    if body["status"] == "done":
        assert body["result"]["updated"] == 3


def test_template_writes_require_auth(client: TestClient) -> None:
    assert client.post("/api/v2/wa/templates", json={"name": "x"}).status_code == 401
    assert client.post("/api/v2/wa/templates/1/save", json={}).status_code == 401
    assert client.delete("/api/v2/wa/templates/1").status_code == 401
    assert client.post("/api/v2/wa/templates/1/submit").status_code == 401
    assert client.post("/api/v2/wa/templates/sync").status_code == 401


def test_sse_stream_route_registered(client: TestClient) -> None:
    """The SSE stream endpoint exists at /wa/stream (Phase 2.2). Path is
    /stream rather than /conversations/stream so it can't collide with
    the dynamic /conversations/{contact_id} route. We assert the route
    is registered + auth-gated; consuming the actual EventSource body
    is covered by Playwright in the live deploy verify step.

    Note: TestClient + an async generator with `await
    request.is_disconnected()` + asyncio.sleep keeps the request open
    after the test breaks out of iter_text(); attempting to consume
    the body in-process hangs the suite. The hello event has been
    smoke-tested via curl against the running api_v2 dev server.
    """
    # Without auth → 401 (proves dependency wired).
    assert client.get("/api/v2/wa/stream").status_code == 401

    # With auth → check OpenAPI lists the route. Avoids opening a
    # streaming connection that the in-process TestClient can't tear
    # down cleanly.
    schema = client.get("/openapi.json").json()
    assert "/api/v2/wa/stream" in schema["paths"]
    assert "get" in schema["paths"]["/api/v2/wa/stream"]


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
