"""/api/v2/wa/* — WhatsApp Inbox read endpoints.

Read-side first: list conversations, read a conversation's messages, list
approved templates. Write endpoints (POST text/template, SSE stream)
land in Phase 2.1.

Reuses v1's wa_chats / wa_messages / wa_templates ORM models — no
duplicated business logic. The 24-hour customer-service window is
computed from `WAChat.window_expires_at` (set by the webhook on every
inbound) rather than re-deriving from message timestamps.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_

from api_v2.deps import require_auth
from api_v2.schemas.wa import (
    ConversationDetail,
    ConversationListItem,
    ConversationListResponse,
    SendMessageRequest,
    SendTemplateRequest,
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
from services.wa_sender import WhatsAppSender  # type: ignore[import-not-found]

router = APIRouter(tags=["wa"], dependencies=[Depends(require_auth)])
"""No prefix here — main.py mounts this router at /api/v2/wa to match the
include-time-prefix convention used by the other 4 routers (review fix
#15)."""


# ─── helpers ─────────────────────────────────────────────────────────────


def _is_window_open(expires_at: datetime | None) -> bool:
    """A conversation's 24h customer-service window is open iff the chat
    has a future `window_expires_at`. The webhook sets this to `now+24h`
    on every inbound message; nothing else extends it."""
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


_VAR_RE = re.compile(r"\{\{\s*([0-9]+|[a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _extract_variables(template: WATemplate) -> list[str]:
    """Pull placeholder names out of every text-bearing field on the
    template — body, header, footer, buttons, AND the `components`
    JSON column (used by the newer template builder; review fix #3).

    WhatsApp templates use either positional ({{1}}, {{2}}) or named
    ({{first_name}}) placeholders. Returns the deduped list in
    first-appearance order so the variables form renders inputs in the
    same sequence the user reads the template body. Whitespace inside
    {{ }} is tolerated.
    """
    sources: list[str] = []
    for field in ("body_text", "header_text", "footer_text"):
        v = getattr(template, field, None)
        if v:
            sources.append(str(v))

    for btn in template.buttons or []:
        if isinstance(btn, dict):
            sources.extend(str(btn.get(k, "")) for k in ("text", "url", "phone_number"))

    # The `components` JSON column may contain {{ }} placeholders inside
    # nested .text / .parameters fields. Stringify the whole structure
    # and run the regex over it — cheaper and more complete than walking
    # every possible Meta-template-builder shape.
    if template.components:
        try:
            sources.append(json.dumps(template.components, default=str))
        except Exception:
            pass

    seen: list[str] = []
    for src in sources:
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
    page: Annotated[int, Query(ge=0)] = 0,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ConversationListResponse:
    """Active conversations — newest activity first, paginated.

    Search and archived filters apply at the SQL layer (review fixes
    #1 + #2): a JOIN to Contact lets ILIKE filter on name/company
    without pulling every chat into Python.
    """
    db = get_db()
    try:
        q = (
            db.query(WAChat, Contact)
            .join(Contact, Contact.id == WAChat.contact_id)
            .filter(WAChat.is_archived.is_(archived))
        )
        if search:
            term = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    Contact.first_name.ilike(term),
                    Contact.last_name.ilike(term),
                    Contact.company.ilike(term),
                )
            )

        total = q.count()
        total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
        # Clamp out-of-range page to the last available page (matches
        # contacts router behavior — review fix Mn3 in earlier phase).
        effective_page = min(page, max(0, total_pages - 1)) if total else 0

        rows = (
            q.order_by(WAChat.last_message_at.desc().nullslast())
            .offset(effective_page * page_size)
            .limit(page_size)
            .all()
        )
        items = [
            ConversationListItem(
                contact_id=chat.contact_id,
                contact_name=_full_name(contact),
                contact_company=contact.company or "",
                last_message_at=chat.last_message_at,
                last_message_preview=chat.last_message_preview or "",
                unread_count=chat.unread_count or 0,
                window_expires_at=chat.window_expires_at,
                window_open=_is_window_open(chat.window_expires_at),
            )
            for chat, contact in rows
        ]
        return ConversationListResponse(
            conversations=items,
            total=total,
            page=effective_page,
            page_size=page_size,
            total_pages=total_pages,
        )
    finally:
        db.close()


@router.get("/conversations/{contact_id}", response_model=ConversationDetail)
def get_conversation(
    contact_id: str,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> ConversationDetail:
    """Full conversation — contact info + ordered message list.

    Returns the most-recent `limit` messages (default 200, max 1000),
    chronologically ordered for the chat panel. Review fix #4: previously
    this loaded every message, which broke down on long-running chats.

    Returns 404 if the contact doesn't exist; returns an empty messages
    list if the contact exists but has never been messaged on WhatsApp.
    """
    db = get_db()
    try:
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")

        chat = db.query(WAChat).filter(WAChat.contact_id == contact_id).first()

        # Newest-first slice -> reverse to chronological for the UI.
        recent = (
            db.query(WAMessage)
            .filter(WAMessage.contact_id == contact_id)
            .order_by(WAMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        messages_q = list(reversed(recent))
        messages = [WAMessageOut.model_validate(m) for m in messages_q]

        last_inbound_at = None
        for m in reversed(messages_q):
            if m.direction in {"in", "incoming", "received"}:
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


# ─── write endpoints (Phase 2.1) ─────────────────────────────────────────


def _phone_for(contact: Contact) -> str | None:
    """Pick the best `to_phone` value for the WhatsApp Cloud API.

    Prefer `wa_id` (already E.164 without +) since the webhook stores it
    that way; fall back to the digit-stripped `phone` column.
    """
    if contact.wa_id:
        return contact.wa_id
    if contact.phone:
        return "".join(ch for ch in contact.phone if ch.isdigit()) or None
    return None


def _ensure_chat(db, contact_id: str) -> WAChat:
    """Get-or-create the WAChat row for a contact."""
    chat = db.query(WAChat).filter(WAChat.contact_id == contact_id).first()
    if chat is None:
        chat = WAChat(contact_id=contact_id)
        db.add(chat)
        db.flush()
    return chat


@router.post(
    "/messages",
    response_model=WAMessageOut,
    status_code=status.HTTP_201_CREATED,
)
def send_text_message(req: SendMessageRequest) -> WAMessageOut:
    """Send a plain text reply within an open 24h customer-service window.

    Returns 412 (Precondition Failed) if the window is closed — the
    frontend already gates this client-side via the closed-window CTA,
    but this is the server-side enforcement (Plan D Phase 1.3).
    """
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text must be non-empty")

    db = get_db()
    try:
        contact = db.query(Contact).filter(Contact.id == req.contact_id).first()
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")

        chat = _ensure_chat(db, contact.id)
        if not _is_window_open(chat.window_expires_at):
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail="24h customer-service window is closed; send a template instead",
            )

        to_phone = _phone_for(contact)
        if not to_phone:
            raise HTTPException(
                status_code=400,
                detail="Contact has no phone or wa_id",
            )

        sender = WhatsAppSender()
        ok, wa_message_id, error = sender.send_text(to_phone, text)

        msg = WAMessage(
            chat_id=chat.id,
            contact_id=contact.id,
            direction="out",
            status="sent" if ok else "failed",
            text=text,
            wa_message_id=wa_message_id,
            error_code=None if ok else "send_failed",
            error_detail=None if ok else (error or ""),
            created_at=datetime.now(timezone.utc),
        )
        db.add(msg)

        if ok:
            chat.last_message_at = msg.created_at
            chat.last_message_preview = text[:255]

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        if not ok:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"WhatsApp send failed: {error or 'unknown'}",
            )

        db.refresh(msg)
        return WAMessageOut.model_validate(msg)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post(
    "/template-sends",
    response_model=WAMessageOut,
    status_code=status.HTTP_201_CREATED,
)
def send_template_message(req: SendTemplateRequest) -> WAMessageOut:
    """Send a pre-approved template (works outside the 24h window).

    Templates that succeed open a fresh 24h window — record that on the
    WAChat row so subsequent text replies are unblocked.
    """
    db = get_db()
    try:
        contact = db.query(Contact).filter(Contact.id == req.contact_id).first()
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")

        # Validate the template exists and is approved.
        tmpl = (
            db.query(WATemplate)
            .filter(WATemplate.name == req.template_name)
            .filter(WATemplate.is_draft.is_(False))
            .first()
        )
        if tmpl is None:
            raise HTTPException(status_code=404, detail="Template not found")
        if (tmpl.status or "").upper() != "APPROVED":
            raise HTTPException(
                status_code=400,
                detail=f"Template status is {tmpl.status!r}; only APPROVED can be sent",
            )

        to_phone = _phone_for(contact)
        if not to_phone:
            raise HTTPException(status_code=400, detail="Contact has no phone or wa_id")

        chat = _ensure_chat(db, contact.id)

        sender = WhatsAppSender()
        ok, wa_message_id, error = sender.send_template(
            to_phone,
            template_name=req.template_name,
            lang=req.language or tmpl.language or "en_US",
            variables=list(req.variables or []),
        )

        # Build a preview from the template body so the conversation list
        # shows something meaningful (vs an empty preview).
        preview = (tmpl.body_text or req.template_name)[:255]

        msg = WAMessage(
            chat_id=chat.id,
            contact_id=contact.id,
            direction="out",
            status="sent" if ok else "failed",
            text=preview,
            wa_message_id=wa_message_id,
            error_code=None if ok else "send_failed",
            error_detail=None if ok else (error or ""),
            created_at=datetime.now(timezone.utc),
        )
        db.add(msg)

        if ok:
            chat.last_message_at = msg.created_at
            chat.last_message_preview = preview
            # Successful template sends DO open a new 24h window per
            # Meta's policy when a customer interacts with the template.
            # Conservative: extend the window so the UI unlocks the
            # text composer immediately. The webhook will refine the
            # exact expiry on the next inbound.
            chat.window_expires_at = msg.created_at + timedelta(hours=24)

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        if not ok:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"WhatsApp template send failed: {error or 'unknown'}",
            )

        db.refresh(msg)
        return WAMessageOut.model_validate(msg)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
