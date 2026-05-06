"""Phase 10.9: WhatsApp webhook on the v2 Space.

Mirrors the existing async handler at app/whatsapp/webhook.py, but uses
the v2 sync DB session. Either Space can receive Meta's callbacks since
they share the same Postgres — this just gives operators flexibility on
which URL to point Meta at.

Handles:
  - GET  /webhook/whatsapp — verification handshake
  - POST /webhook/whatsapp — inbound messages + delivery status updates

Inbound message handling intentionally minimal here — the primary path
remains the v1 handler. This v2 endpoint exists so delivery-status
callbacks (which is what we care about for Phase 10.9) are captured even
when Meta is reconfigured to hit the v2 URL.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from services.database import get_db  # type: ignore[import-not-found]
from services.models import (  # type: ignore[import-not-found]
    Contact,
    WAChat,
    WAMessage,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wa-webhook"])

_VERIFY_TOKEN_ENV = "WA_WEBHOOK_VERIFY_TOKEN"
_APP_SECRET_ENV = "WA_APP_SECRET"


def _verify_signature(body: bytes, signature_header: str | None) -> bool:
    """Verify Meta's X-Hub-Signature-256. If WA_APP_SECRET is unset we
    accept all (dev mode) — production must set it."""
    secret = os.environ.get(_APP_SECRET_ENV)
    if not secret:
        return True  # dev: accept unsigned
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


@router.get("/webhook/whatsapp")
def verify_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_challenge: str = Query("", alias="hub.challenge"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
) -> PlainTextResponse:
    """Meta's verification handshake — echo `hub.challenge` if the token matches."""
    expected = os.environ.get(_VERIFY_TOKEN_ENV, "")
    if hub_mode == "subscribe" and hub_verify_token == expected and expected:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request) -> dict[str, bool]:
    """Process inbound + status callbacks from Meta.

    Phase 10.9 focus: delivery status updates (sent / delivered / read /
    failed). When status=failed, we persist `error_code` + `error_detail`
    on the WAMessage row so the chat panel can surface the reason — see
    MessageBubble.tsx which already renders `error_detail` for failed
    rows.
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    db = get_db()
    try:
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value", {}) or {}

                # Inbound — set window + record. (Light-touch; v1 handler
                # is the canonical path. We still update last_inbound on
                # the chat so v2's window-open logic works.)
                for msg in value.get("messages", []) or []:
                    _record_inbound(db, msg, value.get("contacts", []) or [])

                # Status callbacks — the Phase 10.9 win.
                for status_data in value.get("statuses", []) or []:
                    _apply_status_update(db, status_data)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"ok": True}


def _record_inbound(db, msg: dict[str, Any], contacts_info: list[dict[str, Any]]) -> None:
    """Idempotent inbound message persistence — skips duplicates by wa_message_id."""
    wa_message_id = msg.get("id")
    if not wa_message_id:
        return
    existing = db.query(WAMessage).filter(WAMessage.wa_message_id == wa_message_id).first()
    if existing is not None:
        return  # already recorded by v1 handler or a previous webhook delivery

    sender_wa_id = msg.get("from", "")
    msg_type = msg.get("type", "text")
    text = ""
    if msg_type == "text":
        text = (msg.get("text") or {}).get("body", "")
    else:
        text = f"[{msg_type}]"

    contact = db.query(Contact).filter(Contact.wa_id == sender_wa_id).first()
    if contact is None:
        return  # unknown contact — defer to v1 handler for create-on-receive

    chat = db.query(WAChat).filter(WAChat.contact_id == contact.id).first()
    if chat is None:
        return

    now = datetime.now(timezone.utc)
    db.add(WAMessage(
        chat_id=chat.id,
        contact_id=contact.id,
        direction="in",
        status="delivered",
        text=text,
        wa_message_id=wa_message_id,
        created_at=now,
    ))
    chat.last_message_at = now
    chat.last_message_preview = (text or "")[:255]
    chat.window_expires_at = now + timedelta(hours=24)


_STATUS_ORDER = {"queued": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}


def _apply_status_update(db, status_data: dict[str, Any]) -> None:
    """Phase 10.9 core: apply a delivery status callback to the matching
    WAMessage row. Captures error_code + error_detail when status=failed
    so the chat panel can show "Delivery failed: <reason>"."""
    wa_message_id = status_data.get("id")
    new_status = status_data.get("status", "")
    if not (wa_message_id and new_status):
        return

    msg = db.query(WAMessage).filter(WAMessage.wa_message_id == wa_message_id).first()
    if msg is None:
        logger.debug("v2 webhook: unknown message id=%s status=%s", wa_message_id, new_status)
        return

    current = _STATUS_ORDER.get((msg.status or "").lower(), -1)
    incoming = _STATUS_ORDER.get(new_status, -1)
    # Only advance forward — except `failed` which can override anything.
    if incoming > current or new_status == "failed":
        msg.status = new_status

    errors = status_data.get("errors", []) or []
    if errors:
        first = errors[0] or {}
        # Meta sometimes nests the human-readable detail under
        # error_data.details — pick the most informative thing.
        err_data = first.get("error_data") or {}
        detail = (
            err_data.get("details")
            or first.get("title")
            or first.get("message")
            or ""
        )
        code = first.get("code")
        msg.error_code = str(code) if code is not None else (msg.error_code or "")
        msg.error_detail = detail or (msg.error_detail or "")
        logger.info(
            "v2 webhook: message=%s set status=%s error=%s detail=%r",
            wa_message_id, new_status, code, detail[:120],
        )
