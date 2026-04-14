"""Per-recipient variable injection for email sends.

One campaign can have many recipients. At fire time, each recipient
needs a merged dict of:

  - shared branding vars (banner_url, address, social links, colors, ...)
  - standard contact fields (first_name, last_name, name, email, company)
  - invoice_url (from EmailAttachment lookup — empty string if none)
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


def load_campaign_attachments(
    db: Session, campaign_id: int | None
) -> dict[str, EmailAttachment]:
    """Pre-fetch all attachments for a campaign, keyed by contact_id.

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
    return {r.contact_id: r for r in rows}


def build_send_variables(
    contact: Contact,
    attachments: dict[str, EmailAttachment],
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge shared config + contact fields + invoice_url + extras.

    Parameters
    ----------
    contact
        The recipient Contact model instance.
    attachments
        Result of :func:`load_campaign_attachments` — a dict mapping
        contact_id → EmailAttachment for the current campaign. Only
        ``kind='invoice'`` is used for now (maps to ``invoice_url``).
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

    # Invoice attachment → invoice_url (empty string if none)
    att = attachments.get(contact.id)
    base["invoice_url"] = att.signed_url if (att and att.kind == "invoice") else ""

    if extra:
        base.update(extra)

    return base
