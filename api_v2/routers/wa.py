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
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_

from api_v2.deps import require_auth
from api_v2.schemas.wa import (
    ConversationDetail,
    ConversationListItem,
    ConversationListResponse,
    SendMessageRequest,
    SendTemplateRequest,
    TemplateUpsert,
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
from services.wa_template_builder import build_components  # type: ignore[import-not-found]
from api_v2.services.job_store import get_job_store

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


# ─── tier inference (Phase 4.0) ──────────────────────────────────────────
#
# Mirrors hf_dashboard/pages/wa_template_studio.py::_infer_tier so api_v2
# can compute the same tier label without importing gradio. Phase 5+
# moves these sets to YAML (audit B17). Until then, treat divergence
# from v1 as a build-time bug — both must update together.

_COMPANY_TIER_NAMES: frozenset[str] = frozenset({
    "b2b_fiber_intro",
    "b2b_introduction",
    "followup_interest",
    "hello_world",
    "interactive_whatsap_buttons_new",
    "thank_you_note",
    "welcome_message",
})

_PRODUCT_TIER_NAMES: frozenset[str] = frozenset({
    "order_confirmation",
    "order_delivered",
    "order_tracking",
    "order_shipped",
})


def _infer_tier(name: str, meta_category: str | None) -> str:
    """company / category / product / utility. UTILITY beats name lookup."""
    if (meta_category or "").upper() == "UTILITY":
        return "utility"
    nl = re.sub(r"_v\d+$", "", (name or "").lower())
    if nl in _COMPANY_TIER_NAMES:
        return "company"
    if nl in _PRODUCT_TIER_NAMES:
        return "product"
    if nl.endswith("_overview") or "_range_overview" in nl:
        return "category"
    return "company"


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


def _template_to_out(t: WATemplate) -> WATemplateOut:
    return WATemplateOut(
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
        is_draft=bool(t.is_draft),
        tier=_infer_tier(t.name, t.category),
        rejection_reason=t.rejection_reason or "",
        submitted_at=t.submitted_at,
        quality_score=t.quality_score,
        buttons=list(t.buttons or []),
    )


@router.get("/templates", response_model=WATemplatesResponse)
def list_templates(
    category: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    tier: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    include_drafts: Annotated[bool, Query()] = False,
) -> WATemplatesResponse:
    """Templates list. Defaults match the Send-Template sheet's needs:
    APPROVED, non-draft only. Phase 4.0 added flags so the Template
    Studio list can include drafts and filter by tier/search.

    Pass `include_drafts=true` to also return draft rows. Pass an
    explicit `status` to filter by Meta status (APPROVED / PENDING /
    REJECTED). `tier` filters post-query since tier is computed.
    """
    db = get_db()
    try:
        q = db.query(WATemplate)
        if not include_drafts:
            q = q.filter(WATemplate.is_draft.is_(False))
        if status_filter:
            q = q.filter(WATemplate.status == status_filter)
        elif not include_drafts:
            # Original 2.0 behavior: approved-only when drafts excluded.
            q = q.filter(WATemplate.status == "APPROVED")
        if category:
            q = q.filter(WATemplate.category == category)
        if search:
            q = q.filter(WATemplate.name.ilike(f"%{search}%"))
        rows = q.order_by(WATemplate.name.asc()).all()
        out = [_template_to_out(t) for t in rows]
        if tier:
            out = [o for o in out if o.tier == tier]
        return WATemplatesResponse(templates=out, total=len(out))
    finally:
        db.close()


@router.get("/templates/{template_id}", response_model=WATemplateOut)
def get_template(template_id: int) -> WATemplateOut:
    """Full template record for the Phase 4 editor."""
    db = get_db()
    try:
        t = db.query(WATemplate).filter(WATemplate.id == template_id).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return _template_to_out(t)
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
            header_variables=list(req.header_variables or []),
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


# ─── SSE inbound stream (Phase 2.2) ──────────────────────────────────────


_SSE_POLL_SECONDS = 5
"""How often the SSE loop checks the DB for new wa_messages rows. Picked
to be unobtrusive on Postgres while still feeling live to the user
(previous client-side polling was 15-30s)."""


def _serialize_sse_event(kind: str, payload: dict) -> str:
    """Format a Server-Sent Event chunk per the EventSource spec."""
    import json as _json

    return f"event: {kind}\ndata: {_json.dumps(payload, default=str)}\n\n"


@router.get("/stream")
async def stream_conversations(request: Request) -> StreamingResponse:
    """Server-Sent Events feed for live conversation updates.

    The endpoint polls wa_messages every few seconds for rows newer
    than the per-connection watermark and emits one event per affected
    contact. The frontend invalidates the matching React Query keys
    instead of continuing to poll on a timer (Phase 2.2).

    Why DB polling instead of pub/sub: the WhatsApp webhook lives on
    v1's process, not api_v2. Both share the same Postgres, so the
    only cross-process signal we have is the wa_messages table itself.
    Phase 5 (after v1 retires) can move to in-process asyncio queues
    when the webhook lands in api_v2 directly.
    """

    async def event_gen() -> AsyncIterator[str]:
        # Initial watermark: only stream events that arrive AFTER the
        # connection opens. Existing messages are already on the page.
        watermark = datetime.now(timezone.utc)
        # Send a hello event so the client can confirm the stream is alive.
        yield _serialize_sse_event("hello", {"server_time": watermark.isoformat()})

        while True:
            if await request.is_disconnected():
                break

            db = get_db()
            try:
                rows = (
                    db.query(WAMessage.contact_id, WAMessage.direction, WAMessage.created_at)
                    .filter(WAMessage.created_at > watermark)
                    .order_by(WAMessage.created_at.asc())
                    .all()
                )
            finally:
                db.close()

            for contact_id, direction, created_at in rows:
                yield _serialize_sse_event(
                    "message",
                    {
                        "contact_id": contact_id,
                        "direction": direction if direction in {"in", "out"} else direction,
                        "created_at": created_at,
                    },
                )
                if created_at and created_at.replace(
                    tzinfo=created_at.tzinfo or timezone.utc
                ) > watermark:
                    watermark = created_at.replace(
                        tzinfo=created_at.tzinfo or timezone.utc
                    )

            # Heartbeat keeps proxies (HF reverse proxy) from idling
            # the connection out at 30-60s.
            yield ": heartbeat\n\n"

            try:
                await asyncio.sleep(_SSE_POLL_SECONDS)
            except asyncio.CancelledError:
                break

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx/HF proxy: don't buffer
            "Connection": "keep-alive",
        },
    )


# ─── Template Studio CRUD (Phase 4.1a) ───────────────────────────────────


def _next_clone_name(db, base_name: str) -> str:
    """Find the next available `<base>_vN` suffix for clone-on-edit.

    Strips any existing `_vN` from `base_name` first so editing a
    template that's already a clone (e.g. `welcome_message_v2`) creates
    `welcome_message_v3`, not `welcome_message_v2_v2`. Mirrors v1's
    studio behavior.
    """
    bare = re.sub(r"_v\d+$", "", base_name or "")
    existing = {
        row[0]
        for row in db.query(WATemplate.name)
        .filter(WATemplate.name.like(f"{bare}_v%"))
        .all()
    }
    n = 2
    while f"{bare}_v{n}" in existing:
        n += 1
    return f"{bare}_v{n}"


def _apply_template_fields(t: WATemplate, body: TemplateUpsert) -> None:
    """Mutate `t` from a TemplateUpsert payload. Used by both create and
    save paths so the field list stays in one place."""
    t.language = body.language or "en_US"
    t.category = body.category or "MARKETING"
    t.body_text = body.body_text or ""
    t.header_format = body.header_format
    t.header_text = body.header_text
    t.header_asset_url = body.header_asset_url
    t.footer_text = body.footer_text
    t.buttons = list(body.buttons or [])


@router.post(
    "/templates",
    response_model=WATemplateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_template(body: TemplateUpsert) -> WATemplateOut:
    """Create a new draft template. `name` must be unique."""
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    name = body.name.strip()

    db = get_db()
    try:
        existing = db.query(WATemplate).filter(WATemplate.name == name).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Template name {name!r} already exists",
            )

        t = WATemplate(name=name, status=None, is_draft=True, variables=[])
        _apply_template_fields(t, body)
        db.add(t)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(t)
        return _template_to_out(t)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post("/templates/{template_id}/save", response_model=WATemplateOut)
def save_template(template_id: int, body: TemplateUpsert) -> WATemplateOut:
    """Save edits to a template.

    Clone-on-edit policy: if the target template is APPROVED (or in any
    Meta-acknowledged state — PENDING / APPROVED / REJECTED), saving
    creates a fresh DRAFT clone with name `<base>_vN` instead of
    mutating the immutable submitted record. This protects a sent
    template from accidental edits.

    A draft is mutated in place.
    """
    db = get_db()
    try:
        t = db.query(WATemplate).filter(WATemplate.id == template_id).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Template not found")

        if t.is_draft and not t.status:
            # Draft path: in-place edit.
            _apply_template_fields(t, body)
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            db.refresh(t)
            return _template_to_out(t)

        # Clone-on-edit path: original is immutable.
        clone_name = _next_clone_name(db, t.name)
        clone = WATemplate(name=clone_name, status=None, is_draft=True, variables=[])
        # Start from the original's fields, then overlay the request body.
        clone.language = t.language or "en_US"
        clone.category = t.category or "MARKETING"
        clone.body_text = t.body_text or ""
        clone.header_format = t.header_format
        clone.header_text = t.header_text
        clone.header_asset_url = t.header_asset_url
        clone.footer_text = t.footer_text
        clone.buttons = list(t.buttons or [])
        _apply_template_fields(clone, body)
        db.add(clone)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(clone)
        return _template_to_out(clone)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Note on route ordering: `/templates/sync` is a static path; FastAPI
# matches static-path routes before dynamic-segment ones registered
# later in the file. We declare /templates/sync ABOVE the
# /templates/{template_id}/submit endpoint just to keep the related
# write paths together, but the path discriminator is unambiguous so
# order doesn't actually matter here.


def _spec_from_template(t: WATemplate) -> dict:
    """Convert a WATemplate row to v1's build_components spec dict."""
    spec: dict = {"body": {"text": t.body_text or ""}}
    fmt = (t.header_format or "").upper()
    if fmt == "TEXT" and t.header_text:
        spec["header"] = {"type": "TEXT", "text": t.header_text}
    elif fmt in {"IMAGE", "DOCUMENT", "VIDEO"} and t.header_asset_url:
        spec["header"] = {"type": fmt, "url": t.header_asset_url}
    if t.footer_text:
        spec["footer"] = {"text": t.footer_text}
    if t.buttons:
        spec["buttons"] = list(t.buttons)
    return spec


@router.post("/templates/{template_id}/submit", response_model=WATemplateOut)
def submit_template_to_meta(template_id: int) -> WATemplateOut:
    """Submit a draft template to Meta's WABA API for approval.

    On success: flips is_draft=false, sets status to whatever Meta
    returned (typically PENDING), stores the Meta template id, and
    stamps submitted_at.

    On Meta error: returns 502 with the error detail. The local row
    stays a draft so the user can edit and re-submit. Phase 4.1b
    scope: actual Meta API hits happen here — the user must opt in by
    clicking Submit in the Studio. Tests stub the WhatsAppSender so
    we never call live Meta in CI.
    """
    db = get_db()
    try:
        t = db.query(WATemplate).filter(WATemplate.id == template_id).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Template not found")
        if not t.is_draft:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Template is already submitted; create a new draft to revise",
            )
        if not (t.body_text or "").strip():
            raise HTTPException(status_code=400, detail="body_text is required")

        components = build_components(_spec_from_template(t))
        sender = WhatsAppSender()
        ok, data, err = sender.create_template(
            name=t.name,
            category=(t.category or "MARKETING").upper(),
            language=t.language or "en_US",
            components=components,
        )
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Meta rejected: {err}",
            )

        t.is_draft = False
        t.status = (data or {}).get("status", "PENDING")
        t.meta_template_id = str((data or {}).get("id") or "") or None
        t.submitted_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(t)
        return _template_to_out(t)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _run_template_sync(job_id: str) -> None:
    """BackgroundTasks worker for /templates/sync. Wraps v1's
    sync_templates_from_meta with JobStore status updates."""
    import logging as _logging

    log = _logging.getLogger("api_v2.wa.sync")
    store = get_job_store()
    store.update(job_id, status="running", message="Pulling from Meta…", progress=10)

    db = get_db()
    try:
        sender = WhatsAppSender()
        result = sender.sync_templates_from_meta(db)
        store.update(
            job_id,
            status="done",
            progress=100,
            message=str(result.get("message") or "Sync complete"),
            result=result if isinstance(result, dict) else {"raw": str(result)},
        )
    except Exception as e:
        log.exception("template sync job %s failed", job_id)
        store.update(
            job_id,
            status="failed",
            message=str(e)[:500],
            result={"errors": [str(e)]},
        )
    finally:
        db.close()


@router.post("/templates/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_templates(background_tasks: BackgroundTasks) -> dict:
    """Queue a Meta-template sync. Returns a job_id; poll
    /api/v2/jobs/{job_id}/status. The actual Meta API call happens
    in the background — request returns immediately.
    """
    store = get_job_store()
    job_id = store.create(job_type="template_sync", message="Queued")
    background_tasks.add_task(_run_template_sync, job_id)
    return {"job_id": job_id}


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_template(template_id: int) -> None:
    """Delete a draft template. Submitted templates (PENDING / APPROVED
    / REJECTED) are immutable — deletion would orphan Meta's record.
    """
    db = get_db()
    try:
        t = db.query(WATemplate).filter(WATemplate.id == template_id).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Template not found")
        if not t.is_draft or t.status:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Submitted templates cannot be deleted; create a new draft instead",
            )
        db.delete(t)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
