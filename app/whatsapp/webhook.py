"""WhatsApp webhook handler for Meta Cloud API.

Handles:
- GET /webhook/whatsapp  — verification handshake
- POST /webhook/whatsapp — inbound messages + delivery status updates
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Contact, WhatsAppConsentStatus
from app.db.session import get_db
from app.whatsapp.models import WAChat, WAMessage, WAMessageDirection, WAMessageStatus
from app.whatsapp.utils import normalize_phone

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp-webhook"])

DBSession = Annotated[AsyncSession, Depends(get_db)]


# ------------------------------------------------------------------
# Webhook verification (Meta handshake)
# ------------------------------------------------------------------


@router.get("/webhook/whatsapp")
async def verify_webhook(
    mode: str | None = Query(None, alias="hub.mode"),
    challenge: str | None = Query(None, alias="hub.challenge"),
    token: str | None = Query(None, alias="hub.verify_token"),
) -> PlainTextResponse:
    """Meta webhook verification handshake."""
    if mode == "subscribe" and token == settings.wa_verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(content=challenge or "")
    logger.warning("WhatsApp webhook verification failed: mode=%s", mode)
    raise HTTPException(status_code=403, detail="Verification failed")


# ------------------------------------------------------------------
# Webhook reception (inbound messages + status updates)
# ------------------------------------------------------------------


def _verify_signature(body: bytes, signature: str | None) -> bool:
    """Verify the X-Hub-Signature-256 header from Meta."""
    if not settings.wa_app_secret:
        return True  # Skip verification if app secret not configured
    if not signature:
        return False
    expected = hmac.new(
        settings.wa_app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request, db: DBSession) -> dict[str, bool]:
    """Receive inbound WhatsApp messages and delivery status updates."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not _verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            # Handle inbound messages
            messages = value.get("messages", [])
            contacts_info = value.get("contacts", [])
            if messages:
                await _handle_inbound_messages(db, messages, contacts_info)

            # Handle delivery status updates
            statuses = value.get("statuses", [])
            if statuses:
                await _handle_status_updates(db, statuses)

    return {"ok": True}


# ------------------------------------------------------------------
# Inbound message processing
# ------------------------------------------------------------------


async def _handle_inbound_messages(
    db: AsyncSession,
    messages: list[dict[str, Any]],
    contacts_info: list[dict[str, Any]],
) -> None:
    """Process inbound messages from WhatsApp."""
    # Build a lookup from wa_id to profile name
    profile_names: dict[str, str] = {}
    for c in contacts_info:
        wa_id = c.get("wa_id", "")
        name = c.get("profile", {}).get("name", "")
        if wa_id:
            profile_names[wa_id] = name

    for msg in messages:
        wa_message_id = msg.get("id")
        if not wa_message_id:
            continue

        # Check for duplicate (idempotency)
        existing = await db.execute(
            select(WAMessage).where(WAMessage.wa_message_id == wa_message_id)
        )
        if existing.scalar_one_or_none():
            logger.debug("Duplicate message skipped: %s", wa_message_id)
            continue

        sender_wa_id = msg.get("from", "")
        msg_type = msg.get("type", "text")
        profile_name = profile_names.get(sender_wa_id, "")

        # Extract message content
        text = ""
        media_type = None
        media_id = None
        media_caption = None

        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type in ("image", "document", "audio", "video"):
            media_data = msg.get(msg_type, {})
            media_type = msg_type
            media_id = media_data.get("id")
            media_caption = media_data.get("caption")
            text = media_caption or f"[{msg_type}]"
        else:
            # reaction, location, sticker, etc. — store as text
            text = f"[{msg_type}]"

        # Find or create contact
        contact = await _get_or_create_contact(db, sender_wa_id, profile_name)

        # Ensure chat exists
        chat = await _ensure_chat(db, contact.id)

        # Record message
        now = datetime.now(timezone.utc)
        message = WAMessage(
            chat_id=chat.id,
            contact_id=contact.id,
            direction=WAMessageDirection.INBOUND,
            status=WAMessageStatus.DELIVERED,
            text=text,
            wa_message_id=wa_message_id,
            media_type=media_type,
            media_id=media_id,
            media_caption=media_caption,
        )
        db.add(message)

        # Update contact timestamps
        contact.last_wa_inbound_at = now
        if profile_name and not contact.wa_profile_name:
            contact.wa_profile_name = profile_name

        # Update chat state
        chat.last_message_at = now
        chat.last_message_preview = text[:255] if text else None
        chat.unread_count = (chat.unread_count or 0) + 1
        chat.window_expires_at = now + timedelta(hours=24)

        await db.flush()

        logger.info(
            "Inbound WhatsApp message recorded: contact_id=%d, wa_msg=%s",
            contact.id,
            wa_message_id,
        )


async def _get_or_create_contact(
    db: AsyncSession, wa_id: str, profile_name: str
) -> Contact:
    """Find an existing contact by wa_id or phone, or create a new one."""
    # Try by wa_id first
    result = await db.execute(select(Contact).where(Contact.wa_id == wa_id))
    contact = result.scalar_one_or_none()
    if contact:
        return contact

    # Try by normalized phone
    try:
        normalized = normalize_phone(wa_id)
        result = await db.execute(select(Contact).where(Contact.phone == normalized))
        contact = result.scalar_one_or_none()
        if contact:
            contact.wa_id = wa_id
            return contact
    except ValueError:
        pass

    # Create new contact
    contact = Contact(
        email=f"wa_{wa_id}@whatsapp.placeholder",  # placeholder — WhatsApp contacts may not have email
        name=profile_name or None,
        phone=wa_id,
        wa_id=wa_id,
        wa_profile_name=profile_name or None,
        wa_consent_status=WhatsAppConsentStatus.OPTED_IN,
    )
    db.add(contact)
    await db.flush()
    logger.info("Created new contact from WhatsApp: id=%d, wa_id=%s", contact.id, wa_id)
    return contact


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


# ------------------------------------------------------------------
# Status update processing
# ------------------------------------------------------------------


async def _handle_status_updates(
    db: AsyncSession, statuses: list[dict[str, Any]]
) -> None:
    """Process delivery status updates (sent, delivered, read, failed)."""
    from app.whatsapp.models import WAMessageStatusEvent

    for status_data in statuses:
        wa_message_id = status_data.get("id")
        status_str = status_data.get("status", "")

        if not wa_message_id or not status_str:
            continue

        # Find the message
        result = await db.execute(
            select(WAMessage).where(WAMessage.wa_message_id == wa_message_id)
        )
        message = result.scalar_one_or_none()
        if not message:
            logger.debug("Status update for unknown message: %s", wa_message_id)
            continue

        # Map status string to enum (only advance forward)
        status_order = {"queued": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}
        new_order = status_order.get(status_str, -1)
        current_order = status_order.get(message.status.value, -1)

        if new_order > current_order or status_str == "failed":
            try:
                message.status = WAMessageStatus(status_str)
            except ValueError:
                pass

        # Extract error info if failed
        error_code = None
        error_detail = None
        errors = status_data.get("errors", [])
        if errors:
            error_code = str(errors[0].get("code", ""))
            error_detail = errors[0].get("title", "")
            message.error_code = error_code
            message.error_detail = error_detail

        # Record status event
        event = WAMessageStatusEvent(
            message_id=message.id,
            status=status_str,
            error_code=error_code,
            error_detail=error_detail,
        )
        db.add(event)

        logger.debug(
            "Status update: wa_msg=%s status=%s", wa_message_id, status_str
        )
