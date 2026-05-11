"""/api/v2/email — render-preview + single-contact test sends (Phase 7.1).

Two endpoints, both new:

1. POST /api/v2/email/render-preview — server-side Jinja render (subject +
   HTML body) for the live preview iframes used by EmailSendPage,
   ComposeTab, and EmailTemplateEditor. Server-side because Jinja2 only
   ships server-side and our seeded templates use {% extends %}.

2. POST /api/v2/email/test-sends — fires ONE email to ONE contact via the
   same `EmailSender.send_email` + `render_template_by_slug` path used by
   v1's `_on_test_send`. Writes a single `email_sends` row with
   `campaign_id=NULL` (NOT a 1-recipient broadcast) and uses the
   per-day `generate_idempotency_key("single_send", contact_id)` window.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from api_v2.deps import require_auth
from api_v2.schemas.email_send import (
    RenderPreviewRequest,
    RenderPreviewResponse,
    TestSendRequest,
    TestSendResponse,
)

from services.database import get_db  # type: ignore[import-not-found]
from services.email_personalization import build_send_variables  # type: ignore[import-not-found]
from services.email_sender import (  # type: ignore[import-not-found]
    EmailSender,
    generate_idempotency_key,
    render_template_by_slug,
    render_template_string,
)
from services.models import (  # type: ignore[import-not-found]
    Contact,
    EmailSend,
    EmailTemplate,
)


log = logging.getLogger(__name__)


router = APIRouter(tags=["email_send"], dependencies=[Depends(require_auth)])


def _coerce_vars(vars_: dict[str, str]) -> dict[str, str]:
    """Defensive copy + coerce non-str values to str — Jinja2 happily
    renders ints/None but the email body templates expect strings."""
    return {str(k): "" if v is None else str(v) for k, v in (vars_ or {}).items()}


def _stub_contact() -> Contact:
    """Bare Contact for previews where no real recipient is selected."""
    return Contact(
        id="preview",
        email="preview@example.com",
        first_name="Sample",
        last_name="Customer",
        company="Sample Company",
    )


@router.post("/email/render-preview", response_model=RenderPreviewResponse)
def render_preview(req: RenderPreviewRequest) -> RenderPreviewResponse:
    """Render `template_id` against `variables` (+ optional contact context).

    Returns the rendered subject + body HTML. The frontend feeds the HTML
    into a sandboxed `<iframe srcDoc>` for preview. We intentionally run
    `EmailSender._preprocess_html` so what the user sees matches what the
    sender would write to Gmail (font @import handling, etc.).
    """
    db = get_db()
    try:
        tpl = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.id == req.template_id)
            .first()
        )
        if tpl is None:
            raise HTTPException(status_code=404, detail="Email template not found")

        # Resolve contact context if provided; otherwise fall back to a stub
        # so {{first_name}}-style placeholders still render to something
        # readable instead of empty strings.
        contact: Contact | None = None
        if req.contact_id:
            contact = (
                db.query(Contact)
                .filter(Contact.id == req.contact_id)
                .first()
            )
            if contact is None:
                raise HTTPException(status_code=404, detail="Contact not found")

        merged = build_send_variables(
            contact or _stub_contact(),
            attachments={},
            extra=_coerce_vars(req.variables),
        )

        try:
            if req.html_content_override is not None:
                rendered_html = render_template_string(
                    req.html_content_override, merged
                )
            else:
                rendered_html = render_template_by_slug(tpl.slug, merged)

            subject_src = (
                req.subject_template_override
                if req.subject_template_override is not None
                else (tpl.subject_template or "")
            )
            rendered_subject = render_template_string(subject_src, merged)
        except Exception as e:
            log.exception("render_preview failed for template %s", tpl.slug)
            raise HTTPException(
                status_code=500, detail=f"Render failed: {e}"
            ) from e

        sender = EmailSender()
        rendered_html = sender._preprocess_html(rendered_html)

        return RenderPreviewResponse(html=rendered_html, subject=rendered_subject)
    finally:
        db.close()


@router.post(
    "/email/test-sends",
    response_model=TestSendResponse,
    status_code=status.HTTP_201_CREATED,
)
def test_send(req: TestSendRequest) -> TestSendResponse:
    """Send one email to one contact. NOT a broadcast — `campaign_id=NULL`.

    Per-day idempotency: a second click within the same UTC day for the
    same (template, contact) returns the existing `email_send_id` without
    firing Gmail again. Workaround for the founder: change a variable or
    wait until tomorrow UTC. A "Force resend" affordance is Phase 8.
    """
    db = get_db()
    try:
        tpl = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.id == req.template_id)
            .first()
        )
        if tpl is None:
            raise HTTPException(status_code=404, detail="Email template not found")

        contact = (
            db.query(Contact).filter(Contact.id == req.contact_id).first()
        )
        if contact is None:
            raise HTTPException(status_code=404, detail="Contact not found")
        if not (contact.email or "").strip():
            raise HTTPException(
                status_code=400, detail="Contact has no email address"
            )

        # Per-day dedup window: one row per (single_send, contact, template, day).
        # `template_id` MUST be part of the key — without it, sending the
        # welcome template earlier today blocks an order_shipped send to the
        # same contact later today (the user-reported "duplicate, already
        # sent today" false positive).
        idem_key = generate_idempotency_key(
            "single_send", contact.id, str(req.template_id)
        )
        existing = (
            db.query(EmailSend)
            .filter(EmailSend.idempotency_key == idem_key)
            .first()
        )
        # Only short-circuit if the prior attempt actually succeeded. A
        # `failed` row from earlier today (Gmail outage, render bug, etc.)
        # must NOT permanently block retries — we re-use the same row and
        # overwrite its status when the retry runs below.
        if existing is not None and existing.status == "sent":
            return TestSendResponse(
                success=True,
                message=f"already sent earlier today to {contact.email}",
                email_send_id=existing.id,
            )

        sender = EmailSender()
        if not sender.is_configured():
            raise HTTPException(
                status_code=502,
                detail=(
                    "Gmail API not configured (GMAIL_REFRESH_TOKEN unset). "
                    "Set the secret on the HF Space and retry."
                ),
            )

        merged = build_send_variables(
            contact, attachments={}, extra=_coerce_vars(req.variables)
        )
        subject_src = (
            req.subject_override
            if req.subject_override is not None
            else (tpl.subject_template or "")
        )
        try:
            rendered_html = render_template_by_slug(tpl.slug, merged)
            rendered_subject = render_template_string(subject_src, merged)
        except Exception as e:
            log.exception("test_send render failed for slug %s", tpl.slug)
            raise HTTPException(
                status_code=500, detail=f"Render failed: {e}"
            ) from e

        result = sender.send_email(
            to_email=contact.email,
            subject=rendered_subject,
            html_content=rendered_html,
            to_name=(contact.first_name or None),
        )

        # Retry path: if an earlier failed row exists for this key, update
        # it in place — inserting a new row would 23505 on the unique
        # idempotency_key index.
        if existing is not None:
            row = existing
            row.contact_email = contact.email or ""
            row.subject = rendered_subject
            row.status = "sent" if result["success"] else "failed"
            row.error_message = "" if result["success"] else result.get("message", "")
            row.sent_at = datetime.now(timezone.utc) if result["success"] else None
        else:
            row = EmailSend(
                contact_id=contact.id,
                contact_email=contact.email or "",
                campaign_id=None,
                subject=rendered_subject,
                status="sent" if result["success"] else "failed",
                idempotency_key=idem_key,
                error_message="" if result["success"] else result.get("message", ""),
                sent_at=datetime.now(timezone.utc) if result["success"] else None,
            )
            db.add(row)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(row)

        if not result["success"]:
            # Audit row is written; surface the Gmail error to the UI.
            return TestSendResponse(
                success=False,
                message=result.get("message", "Send failed"),
                email_send_id=row.id,
            )

        return TestSendResponse(
            success=True,
            message=f"Sent to {contact.email}",
            email_send_id=row.id,
        )
    finally:
        db.close()
