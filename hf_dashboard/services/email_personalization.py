"""Per-recipient variable injection for email sends.

One campaign can have many recipients. At fire time, each recipient
needs a merged dict of:

  - shared branding vars (banner_url, address, social links, colors, media, ...)
  - standard contact fields (first_name, last_name, name, email, company)
  - one variable per attachment kind (e.g. ``invoice_url``,
    ``price_list_url``) — empty string when no attachment of that
    kind exists for the contact
  - any extra per-send vars the caller passes (order_number, total, ...)

To avoid N DB queries for an N-recipient campaign, the broadcast send
loop should call :func:`load_campaign_attachments` **once** before the
loop and pass the resulting dict into :func:`build_send_variables` per
recipient.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from services.email_shared_config import load_shared_config
from services.models import Contact, EmailAttachment

log = logging.getLogger(__name__)

# Every attachment kind we surface as a `{kind}_url` template variable.
# Keep in sync with `template_seed.ExpectedAttachmentKind`.
_ATTACHMENT_VAR_NAMES = ("invoice", "price_list")


def load_campaign_attachments(
    db: Session, campaign_id: int | None
) -> dict[str, list[EmailAttachment]]:
    """Pre-fetch all attachments for a campaign, keyed by contact_id.

    Returns a mapping ``contact_id -> [EmailAttachment, ...]`` because a
    single contact can have multiple attachments of different kinds for
    the same campaign (e.g. invoice + price_list).

    One query per campaign instead of one per recipient. Returns an
    empty dict when ``campaign_id`` is None (draft compose with no
    attachments yet) or when the campaign has no attachments.
    """
    if not campaign_id:
        return {}
    rows = (
        db.query(EmailAttachment)
        .filter(EmailAttachment.campaign_id == campaign_id)
        .all()
    )
    out: dict[str, list[EmailAttachment]] = {}
    for r in rows:
        out.setdefault(r.contact_id, []).append(r)
    return out


def build_send_variables(
    contact: Contact,
    attachments: dict[str, list[EmailAttachment]],
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge shared config + contact fields + attachment URLs + extras.

    Parameters
    ----------
    contact
        The recipient Contact model instance.
    attachments
        Result of :func:`load_campaign_attachments` — a dict mapping
        contact_id → list of EmailAttachment rows for the current
        campaign. Each attachment's ``kind`` field becomes a template
        variable named ``{kind}_url`` (e.g. ``invoice_url``,
        ``price_list_url``).
    extra
        Optional per-send variables provided by the caller
        (e.g. ``order_number``, ``total``, ``tracking_id``). These are
        merged in last so they can override any default.

    Returns
    -------
    dict
        Fully resolved variable dict ready to pass to the Jinja2
        renderer via :func:`services.email_sender.render_template_by_slug`.
    """
    base: dict[str, Any] = dict(load_shared_config())

    first = (contact.first_name or "").strip()
    last = (contact.last_name or "").strip()
    full_name = (first + " " + last).strip() or "there"

    base.update(
        {
            "first_name": first or "there",
            "last_name": last,
            "name": full_name,
            "email": contact.email or "",
            # Contact's own company name — kept separate from the shared
            # ``company_name`` branding var (Himalayan Fibres).
            "contact_company": contact.company or "",
        }
    )

    # One variable per attachment kind. Defaults:
    #   - invoice_url:    empty string (only present when explicitly attached
    #                     per recipient via the invoice upload flow)
    #   - price_list_url: shared canonical URL from shared.yml — same PDF
    #                     for every recipient, so there's no benefit to
    #                     per-recipient mirroring. Per-recipient
    #                     EmailAttachment row still wins if present (lets
    #                     the founder send a different/older price list to
    #                     a specific contact via the broadcast composer).
    base["invoice_url"] = ""
    base["price_list_url"] = base.get("price_list_pdf_url", "") or ""
    # Config-driven CTA defaults so catalog / sample-request buttons always
    # render with a working link. A per-send value in `extra` still wins
    # (base.update(extra) below). Fixes B3/B4: these CTAs were gated on
    # variables that were never populated, so the buttons rendered empty.
    _catalog = base.get("catalog_pdf_url", "") or ""
    _sample = base.get("sample_request_url", "") or ""
    base["catalog_link"] = _catalog
    base["sample_request_link"] = _sample
    base["sample_form_link"] = _sample
    for att in attachments.get(contact.id, []):
        if att.kind in _ATTACHMENT_VAR_NAMES:
            base[f"{att.kind}_url"] = att.signed_url or ""

    if extra:
        base.update(extra)

    return base
