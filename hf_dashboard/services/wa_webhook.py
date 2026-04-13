"""Inbound WhatsApp message processing.

Ported from app/whatsapp/webhook.py — handles Meta webhook payloads,
creates contacts/chats/messages, updates delivery statuses.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from services.config import get_settings
from services.models import Contact, WAChat, WAMessage

log = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


def normalize_phone(raw: str) -> str:
    """Sanitize phone to E.164-ish format."""
    cleaned = re.sub(r"[^0-9+]", "", (raw or "").strip())
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    cleaned = re.sub(r"[^0-9]", "", cleaned)
    if not cleaned or len(cleaned) < 7 or len(cleaned) > 15:
        raise ValueError(f"Invalid phone: {raw}")
    return cleaned


def verify_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """Verify HMAC-SHA256 webhook signature from Meta."""
    settings = get_settings()
    if not settings.wa_app_secret:
        return True  # Skip if secret not configured
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.wa_app_secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


def process_webhook_payload(db: Session, payload: dict) -> dict:
    """Process a Meta WhatsApp webhook payload.

    Handles inbound messages and delivery status updates.
    Returns summary of what was processed.
    """
    results = {"messages_processed": 0, "statuses_processed": 0, "errors": []}

    entry = payload.get("entry", [])
    for e in entry:
        changes = e.get("changes", [])
        for change in changes:
            value = change.get("value", {})

            # Process inbound messages
            messages = value.get("messages", [])
            contacts_data = value.get("contacts", [])
            for msg in messages:
                try:
                    _handle_inbound_message(db, msg, contacts_data)
                    results["messages_processed"] += 1
                except Exception as ex:
                    log.exception("Error processing inbound message")
                    results["errors"].append(str(ex))

            # Process delivery statuses
            statuses = value.get("statuses", [])
            for status in statuses:
                try:
                    _handle_status_update(db, status)
                    results["statuses_processed"] += 1
                except Exception as ex:
                    log.exception("Error processing status update")
                    results["errors"].append(str(ex))

    db.commit()
    return results


def _handle_inbound_message(db: Session, msg: dict, contacts_data: list[dict]):
    """Process a single inbound WhatsApp message."""
    wa_msg_id = msg.get("id")
    from_phone = msg.get("from", "")
    msg_type = msg.get("type", "text")
    timestamp = msg.get("timestamp", "")

    # Idempotency: skip if already processed
    existing = db.query(WAMessage).filter(WAMessage.wa_message_id == wa_msg_id).first()
    if existing:
        return

    # Extract text
    text = ""
    media_type = None
    media_id = None
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "")
    elif msg_type in ("image", "document", "audio", "video"):
        media_type = msg_type
        media_data = msg.get(msg_type, {})
        media_id = media_data.get("id")
        text = media_data.get("caption", f"[{msg_type}]")
    elif msg_type == "reaction":
        text = msg.get("reaction", {}).get("emoji", "")
    else:
        text = f"[{msg_type}]"

    # Get or create contact
    wa_profile_name = ""
    if contacts_data:
        profile = contacts_data[0].get("profile", {})
        wa_profile_name = profile.get("name", "")

    contact = _get_or_create_contact(db, from_phone, wa_profile_name)

    # Ensure chat
    chat = _ensure_chat(db, contact.id)

    # Create message
    now = datetime.now(timezone.utc)
    message = WAMessage(
        chat_id=chat.id,
        contact_id=contact.id,
        direction="in",
        status="delivered",
        text=text,
        wa_message_id=wa_msg_id,
        media_type=media_type,
        media_id=media_id,
    )
    db.add(message)

    # Update contact + chat state
    contact.last_wa_inbound_at = now
    if wa_profile_name:
        contact.wa_profile_name = wa_profile_name

    chat.last_message_at = now
    chat.last_message_preview = text[:255]
    chat.unread_count = (chat.unread_count or 0) + 1
    chat.window_expires_at = now + timedelta(hours=24)

    db.flush()


def _handle_status_update(db: Session, status: dict):
    """Process a delivery status update (sent, delivered, read, failed)."""
    wa_msg_id = status.get("id")
    new_status = status.get("status", "")

    if not wa_msg_id or not new_status:
        return

    message = db.query(WAMessage).filter(WAMessage.wa_message_id == wa_msg_id).first()
    if not message:
        return

    message.status = new_status

    if new_status == "failed":
        errors = status.get("errors", [])
        if errors:
            message.error_code = str(errors[0].get("code", ""))
            message.error_detail = errors[0].get("title", "")

    db.flush()


def _get_or_create_contact(db: Session, wa_id: str, profile_name: str = "") -> Contact:
    """Find contact by wa_id or phone, or create a new one."""
    # Try by wa_id
    contact = db.query(Contact).filter(Contact.wa_id == wa_id).first()
    if contact:
        return contact

    # Try by normalized phone
    try:
        normalized = normalize_phone(wa_id)
        contact = db.query(Contact).filter(Contact.phone == normalized[-10:]).first()
        if contact:
            contact.wa_id = wa_id
            return contact
    except ValueError:
        pass

    # Create new contact
    name_parts = (profile_name or "").split(" ", 1)
    contact = Contact(
        id=str(uuid.uuid4())[:8],
        email=f"wa_{wa_id}@whatsapp.placeholder",
        first_name=name_parts[0] if name_parts else "",
        last_name=name_parts[1] if len(name_parts) > 1 else "",
        wa_id=wa_id,
        wa_profile_name=profile_name,
        wa_consent_status="opted_in",
        consent_status="pending",
        source="whatsapp_inbound",
    )
    db.add(contact)
    db.flush()
    return contact


def _ensure_chat(db: Session, contact_id: str) -> WAChat:
    """Get or create a WAChat for the contact."""
    chat = db.query(WAChat).filter(WAChat.contact_id == contact_id).first()
    if chat:
        return chat

    chat = WAChat(contact_id=contact_id)
    db.add(chat)
    db.flush()
    return chat
