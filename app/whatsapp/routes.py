"""WhatsApp API routes.

Endpoints for conversations, sending messages, and template management.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Contact
from app.db.session import get_db
from app.whatsapp.models import (
    WAChat,
    WAMessage,
    WAMessageDirection,
    WAMessageStatus,
    WATemplate,
)
from app.whatsapp.schemas import (
    WAChatListResponse,
    WAChatResponse,
    WAMessageResponse,
    WAReplyRequest,
    WASendResult,
    WASendTemplateRequest,
    WASendTextRequest,
    WATemplateResponse,
    WATemplateSyncResult,
)
from app.whatsapp.config import wa_config
from app.whatsapp.service import whatsapp_service
from app.whatsapp.utils import contact_within_24h

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

DBSession = Annotated[AsyncSession, Depends(get_db)]


# ------------------------------------------------------------------
# Conversations
# ------------------------------------------------------------------


@router.get("/chats", response_model=WAChatListResponse)
async def list_chats(
    db: DBSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    archived: bool = False,
) -> WAChatListResponse:
    """List WhatsApp conversations, sorted by most recent activity."""
    # Count total
    count_q = select(func.count(WAChat.id)).where(WAChat.is_archived == archived)
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch chats with contact info
    q = (
        select(WAChat)
        .options(selectinload(WAChat.contact))
        .where(WAChat.is_archived == archived)
        .order_by(WAChat.last_message_at.desc().nullslast())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(q)
    chats = result.scalars().all()

    now = datetime.now(timezone.utc)
    chat_responses = []
    for chat in chats:
        c = chat.contact
        window_open = (
            chat.window_expires_at is not None and chat.window_expires_at > now
        )
        chat_responses.append(
            WAChatResponse(
                id=chat.id,
                contact_id=chat.contact_id,
                contact_name=c.name if c else None,
                contact_phone=c.phone if c else None,
                contact_company=c.company if c else None,
                contact_wa_id=c.wa_id if c else None,
                last_message_at=chat.last_message_at,
                last_message_preview=chat.last_message_preview,
                unread_count=chat.unread_count or 0,
                window_open=window_open,
                is_archived=chat.is_archived,
                created_at=chat.created_at,
            )
        )

    return WAChatListResponse(chats=chat_responses, total=total)


@router.get("/chats/{chat_id}/messages", response_model=list[WAMessageResponse])
async def get_chat_messages(
    chat_id: int,
    db: DBSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[WAMessageResponse]:
    """Get messages for a conversation, oldest first."""
    # Verify chat exists
    chat = await db.get(WAChat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    q = (
        select(WAMessage)
        .where(WAMessage.chat_id == chat_id)
        .order_by(WAMessage.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(q)
    messages = result.scalars().all()

    return [
        WAMessageResponse(
            id=m.id,
            direction=m.direction.value,
            text=m.text,
            status=m.status.value,
            wa_message_id=m.wa_message_id,
            media_type=m.media_type,
            media_path=m.media_path,
            media_caption=m.media_caption,
            error_code=m.error_code,
            error_detail=m.error_detail,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/chats/{chat_id}/reply", response_model=WASendResult)
async def reply_to_chat(
    chat_id: int,
    body: WAReplyRequest,
    db: DBSession,
) -> WASendResult:
    """Reply to an existing conversation with a text message.

    Only works within the 24-hour messaging window.
    """
    chat = await db.get(WAChat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    contact = await db.get(Contact, chat.contact_id)
    if not contact or not contact.wa_id:
        raise HTTPException(status_code=400, detail="Contact has no WhatsApp ID")

    # Check 24h window
    if not contact_within_24h(contact.last_wa_inbound_at):
        raise HTTPException(
            status_code=400,
            detail="Outside 24-hour messaging window. Use a template message instead.",
        )

    return await _send_text_to_contact(db, contact, chat, body.text)


@router.post("/chats/{chat_id}/read")
async def mark_chat_read(chat_id: int, db: DBSession) -> dict[str, bool]:
    """Mark all messages in a chat as read (reset unread count)."""
    chat = await db.get(WAChat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat.unread_count = 0
    return {"ok": True}


# ------------------------------------------------------------------
# Send messages
# ------------------------------------------------------------------


@router.post("/send/text", response_model=WASendResult)
async def send_text(body: WASendTextRequest, db: DBSession) -> WASendResult:
    """Send a text message to a contact. Requires 24h messaging window."""
    contact = await db.get(Contact, body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if not contact.wa_id and not contact.phone:
        raise HTTPException(status_code=400, detail="Contact has no phone/WhatsApp ID")

    # Check 24h window
    if not contact_within_24h(contact.last_wa_inbound_at):
        raise HTTPException(
            status_code=400,
            detail="Outside 24-hour messaging window. Use a template message instead.",
        )

    # Ensure chat
    chat = await _ensure_chat(db, contact.id)
    return await _send_text_to_contact(db, contact, chat, body.text)


@router.post("/send/template", response_model=WASendResult)
async def send_template(
    body: WASendTemplateRequest, db: DBSession
) -> WASendResult:
    """Send a template message to a contact. Works outside the 24h window."""
    contact = await db.get(Contact, body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    to_phone = contact.wa_id or contact.phone
    if not to_phone:
        raise HTTPException(status_code=400, detail="Contact has no phone/WhatsApp ID")

    # Ensure chat
    chat = await _ensure_chat(db, contact.id)

    # Create message record
    now = datetime.now(timezone.utc)
    message = WAMessage(
        chat_id=chat.id,
        contact_id=contact.id,
        direction=WAMessageDirection.OUTBOUND,
        status=WAMessageStatus.QUEUED,
        text=f"[template: {body.template_name}]",
    )
    db.add(message)
    await db.flush()

    # Send via API
    ok, wa_msg_id, error = await whatsapp_service.send_template(
        to_phone=to_phone,
        template_name=body.template_name,
        lang=body.language,
        variables=body.variables or None,
    )

    if ok:
        message.status = WAMessageStatus.SENT
        message.wa_message_id = wa_msg_id
        contact.last_wa_outbound_at = now
        chat.last_message_at = now
        chat.last_message_preview = f"[template: {body.template_name}]"
    else:
        message.status = WAMessageStatus.FAILED
        message.error_detail = error

    return WASendResult(
        ok=ok,
        wa_message_id=wa_msg_id,
        db_message_id=message.id,
        error=error,
    )


# ------------------------------------------------------------------
# Templates
# ------------------------------------------------------------------


@router.get("/templates", response_model=list[WATemplateResponse])
async def list_templates(
    db: DBSession,
    status_filter: str | None = Query(None, alias="status"),
) -> list[WATemplateResponse]:
    """List synced WhatsApp message templates."""
    q = (
        select(WATemplate)
        .where(WATemplate.is_draft.is_(False))
        .order_by(WATemplate.name)
    )
    if status_filter:
        q = q.where(WATemplate.status == status_filter.upper())
    result = await db.execute(q)
    templates = result.scalars().all()
    return [
        WATemplateResponse(
            id=t.id,
            name=t.name,
            language=t.language,
            category=t.category,
            status=t.status,
            quality_score=t.quality_score,
            components=t.components or [],
            last_synced_at=t.last_synced_at,
        )
        for t in templates
    ]


@router.post("/templates/sync", response_model=WATemplateSyncResult)
async def sync_templates(db: DBSession) -> WATemplateSyncResult:
    """Sync templates from Meta WhatsApp Business API."""
    ok, templates_data, error = await whatsapp_service.list_templates()
    if not ok:
        raise HTTPException(status_code=502, detail=f"Meta API error: {error}")

    now = datetime.now(timezone.utc)
    created = 0
    updated = 0
    errors: list[str] = []

    for tpl in templates_data or []:
        name = tpl.get("name", "")
        language = tpl.get("language", "")
        if not name or not language:
            errors.append(f"Skipped template with missing name/language: {tpl}")
            continue

        # Find existing
        result = await db.execute(
            select(WATemplate).where(
                WATemplate.name == name, WATemplate.language == language
            )
        )
        existing = result.scalar_one_or_none()

        qs_raw = tpl.get("quality_score")
        quality_score = qs_raw.get("score") if isinstance(qs_raw, dict) else qs_raw
        rejection = tpl.get("rejected_reason") or ""
        if rejection == "NONE":
            rejection = ""
        if existing:
            existing.category = tpl.get("category")
            existing.status = tpl.get("status")
            existing.quality_score = quality_score
            existing.components = tpl.get("components", [])
            existing.last_synced_at = now
            existing.is_draft = False
            existing.rejection_reason = rejection
            updated += 1
        else:
            new_template = WATemplate(
                name=name,
                language=language,
                category=tpl.get("category"),
                status=tpl.get("status"),
                quality_score=quality_score,
                components=tpl.get("components", []),
                last_synced_at=now,
                is_draft=False,
                rejection_reason=rejection,
            )
            db.add(new_template)
            created += 1

    return WATemplateSyncResult(
        synced=len(templates_data or []),
        created=created,
        updated=updated,
        errors=errors,
    )


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------


@router.get("/health")
async def health_check() -> dict:
    """Check WhatsApp API connectivity."""
    return await whatsapp_service.verify_connection()


# ------------------------------------------------------------------
# Config-driven endpoints (from YAML)
# ------------------------------------------------------------------


@router.get("/quick-replies")
async def list_quick_replies() -> list[dict]:
    """List available quick reply presets from config."""
    return wa_config.list_quick_replies()


@router.get("/quick-replies/{key}")
async def get_quick_reply(key: str) -> dict:
    """Get a specific quick reply text."""
    text = wa_config.get_quick_reply(key)
    if text is None:
        raise HTTPException(status_code=404, detail=f"Quick reply '{key}' not found")
    return {"key": key, "text": text}


@router.get("/template-config/{name}")
async def get_template_config(name: str) -> dict:
    """Get the YAML-defined template schema (variables, use case, etc.)."""
    tpl = wa_config.get_template(name)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"Template config '{name}' not found")
    return tpl.model_dump()


@router.get("/config/labels")
async def get_labels_config() -> dict:
    """Get preset labels and auto-label rules from config."""
    return {
        "preset_labels": [l.model_dump() for l in wa_config.get_preset_labels()],
        "auto_label_rules": [r.model_dump() for r in wa_config.get_auto_label_rules()],
    }


@router.get("/config/validate")
async def validate_config() -> dict:
    """Validate all WhatsApp YAML configs and return issues."""
    return wa_config.validate_all()


@router.post("/config/reload")
async def reload_config() -> dict:
    """Reload WhatsApp YAML configs from disk."""
    wa_config.reload()
    return {"ok": True, "message": "WhatsApp configuration reloaded"}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _ensure_chat(db: AsyncSession, contact_id: int) -> WAChat:
    """Get or create a WAChat for the contact."""
    result = await db.execute(
        select(WAChat).where(WAChat.contact_id == contact_id)
    )
    chat = result.scalar_one_or_none()
    if chat:
        return chat

    chat = WAChat(contact_id=contact_id)
    db.add(chat)
    await db.flush()
    return chat


async def _send_text_to_contact(
    db: AsyncSession, contact: Contact, chat: WAChat, text: str
) -> WASendResult:
    """Send a text message and record it in the database."""
    to_phone = contact.wa_id or contact.phone
    if not to_phone:
        return WASendResult(ok=False, error="Contact has no phone/WhatsApp ID")

    now = datetime.now(timezone.utc)

    # Create message record
    message = WAMessage(
        chat_id=chat.id,
        contact_id=contact.id,
        direction=WAMessageDirection.OUTBOUND,
        status=WAMessageStatus.QUEUED,
        text=text,
    )
    db.add(message)
    await db.flush()

    # Send via API
    ok, wa_msg_id, error = await whatsapp_service.send_text(
        to_phone=to_phone, text=text
    )

    if ok:
        message.status = WAMessageStatus.SENT
        message.wa_message_id = wa_msg_id
        contact.last_wa_outbound_at = now
        chat.last_message_at = now
        chat.last_message_preview = text[:255]
    else:
        message.status = WAMessageStatus.FAILED
        message.error_detail = error

    return WASendResult(
        ok=ok,
        wa_message_id=wa_msg_id,
        db_message_id=message.id,
        error=error,
    )
