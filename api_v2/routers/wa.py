"""/api/v2/wa/* — WhatsApp Inbox read endpoints (Phase 2.0).

Read-side first: list conversations, read a conversation's messages, list
approved templates. Write endpoints (POST text/template, SSE stream)
land in a follow-up commit so the frontend can start consuming the read
shape early.

Reuses v1's wa_chats / wa_messages / wa_templates ORM models — no
duplicated business logic. The 24-hour customer-service window is
computed from `WAChat.window_expires_at` (set by the webhook on every
inbound) rather than re-deriving from message timestamps.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from api_v2.deps import require_auth
from api_v2.schemas.wa import (
    ConversationDetail,
    ConversationListItem,
    ConversationListResponse,
    WAMessageOut,
    WATemplateOut,
    WATemplatesResponse,
)

# Reuse v1's services — single source of truth for the data layer.
from services.database import get_db  # type: ignore[import-not-found]
from services.models import (  # type: ignore[import-not-found]
    Contact,
    WAChat,
    WAMessage,
    WATemplate,
)

router = APIRouter(prefix="/api/v2/wa", tags=["wa"], dependencies=[Depends(require_auth)])


# ─── helpers ─────────────────────────────────────────────────────────────


def _is_window_open(expires_at: datetime | None) -> bool:
    """A conversation's 24h customer-service window is open iff the chat
    has a future `window_expires_at`. The webhook sets this to `now+24h`
    on every inbound message; nothing else extends it. Returning False
    for missing/stale expiry is the conservative default."""
    if expires_at is None:
        return False
    # SQLAlchemy returns naive datetimes from SQLite/Postgres; assume UTC.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


_VAR_RE = re.compile(r"\{\{\s*([0-9]+|[a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _extract_variables(template: WATemplate) -> list[str]:
    """Pull placeholder names out of body/header/buttons.

    WhatsApp templates use either positional ({{1}}, {{2}}) or named
    ({{first_name}}) placeholders. Returns the deduped list in
    first-appearance order so the variables form renders inputs in the
    same sequence the user reads the template body.
    """
    seen: list[str] = []
    candidates: list[str] = []
    candidates.append(template.body_text or "")
    candidates.append(template.header_text or "")
    for btn in template.buttons or []:
        if isinstance(btn, dict):
            candidates.append(str(btn.get("text", "")))
            candidates.append(str(btn.get("url", "")))
    for src in candidates:
        for match in _VAR_RE.findall(src):
            if match not in seen:
                seen.append(match)
    return seen


def _full_name(c: Contact) -> str:
    parts = [c.first_name or "", c.last_name or ""]
    return " ".join(p for p in parts if p).strip() or c.id


# ─── endpoints ───────────────────────────────────────────────────────────


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    search: Annotated[str | None, Query()] = None,
    archived: Annotated[bool, Query()] = False,
) -> ConversationListResponse:
    """Active conversations — newest activity first.

    `archived=True` returns archived chats instead. Search filters by
    contact name/company case-insensitively.
    """
    db = get_db()
    try:
        chats = (
            db.query(WAChat)
            .filter(WAChat.is_archived.is_(archived))
            .order_by(WAChat.last_message_at.desc().nullslast())
            .all()
        )
        # Plan D Phase 1.3 column-narrowing: one bulk Contact lookup
        # rather than N+1 round-trips per chat.
        contact_ids = [c.contact_id for c in chats]
        contacts: dict[str, Contact] = {
            c.id: c
            for c in db.query(Contact).filter(Contact.id.in_(contact_ids)).all()
        }

        items: list[ConversationListItem] = []
        s = (search or "").strip().lower()
        for chat in chats:
            contact = contacts.get(chat.contact_id)
            if contact is None:
                continue  # orphaned chat row — skip
            name = _full_name(contact)
            company = contact.company or ""
            if s and s not in name.lower() and s not in company.lower():
                continue
            items.append(
                ConversationListItem(
                    contact_id=chat.contact_id,
                    contact_name=name,
                    contact_company=company,
                    last_message_at=chat.last_message_at,
                    last_message_preview=chat.last_message_preview or "",
                    unread_count=chat.unread_count or 0,
                    window_expires_at=chat.window_expires_at,
                    window_open=_is_window_open(chat.window_expires_at),
                )
            )
        return ConversationListResponse(conversations=items, total=len(items))
    finally:
        db.close()


@router.get("/conversations/{contact_id}", response_model=ConversationDetail)
def get_conversation(contact_id: str) -> ConversationDetail:
    """Full conversation — contact info + ordered message list.

    Returns 404 if the contact doesn't exist; returns an empty messages
    list if the contact exists but has never been messaged on WhatsApp
    (the frontend uses this state to show 'No conversation yet' + a
    template-send CTA).
    """
    db = get_db()
    try:
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")

        chat = db.query(WAChat).filter(WAChat.contact_id == contact_id).first()

        messages_q = (
            db.query(WAMessage)
            .filter(WAMessage.contact_id == contact_id)
            .order_by(WAMessage.created_at.asc())
            .all()
        )
        messages = [WAMessageOut.model_validate(m) for m in messages_q]

        last_inbound_at = None
        for m in reversed(messages_q):
            if m.direction == "in":
                last_inbound_at = m.created_at
                break

        window_expires_at = chat.window_expires_at if chat else None
        return ConversationDetail(
            contact_id=contact.id,
            contact_name=_full_name(contact),
            contact_company=contact.company or "",
            contact_phone=contact.phone or "",
            contact_wa_id=contact.wa_id,
            consent_status=contact.consent_status or "pending",
            lifecycle=contact.lifecycle or "new_lead",
            window_expires_at=window_expires_at,
            window_open=_is_window_open(window_expires_at),
            last_inbound_at=last_inbound_at,
            messages=messages,
        )
    finally:
        db.close()


@router.get("/templates", response_model=WATemplatesResponse)
def list_templates(
    category: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> WATemplatesResponse:
    """Approved templates available for sending.

    Defaults to `status=APPROVED` and excludes drafts so the inbox UI
    only shows templates that can actually be sent. Pass an explicit
    `status` to override (e.g. for a Template Studio preview).
    """
    db = get_db()
    try:
        q = db.query(WATemplate).filter(WATemplate.is_draft.is_(False))
        if status_filter:
            q = q.filter(WATemplate.status == status_filter)
        else:
            q = q.filter(WATemplate.status == "APPROVED")
        if category:
            q = q.filter(WATemplate.category == category)
        rows = q.order_by(WATemplate.name.asc()).all()
        out = [
            WATemplateOut(
                id=t.id,
                name=t.name,
                language=t.language or "en_US",
                category=t.category,
                status=t.status,
                body_text=t.body_text or "",
                header_format=t.header_format,
                header_asset_url=t.header_asset_url,
                header_text=t.header_text,
                footer_text=t.footer_text,
                variables=_extract_variables(t),
            )
            for t in rows
        ]
        return WATemplatesResponse(templates=out, total=len(out))
    finally:
        db.close()
