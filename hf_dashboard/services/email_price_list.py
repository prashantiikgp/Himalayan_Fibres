"""Price-list attachment helper.

Mirrors a canonical price-list PDF (founder-maintained, hosted on Drive
or wherever) to Supabase Storage on a per-recipient basis, then inserts
one ``email_attachments`` row per recipient with ``kind='price_list'``.
The existing ``build_send_variables`` then surfaces the resulting
signed URL as ``{{ price_list_url }}`` in the template.

Why per-recipient instead of a single shared URL: the existing
audit/dedup pattern keys on ``(campaign_id, contact_id, kind)``, and
each recipient's signed URL also auto-expires after 1 year — keeping
this consistent with how ``kind='invoice'`` already works.

Sources supported
-----------------
- ``local`` — read bytes from a path on disk (dev / staging)
- ``url``   — fetch via HTTPS (Drive direct-download link, public PDF)

The single-source-of-truth path is read from
``config/email/shared.yml::shared.price_list_pdf_url`` if not passed
explicitly. Founder updates that value once per quarter when a new
price list is published.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import requests

from services.models import EmailAttachment
from services.supabase_storage import upload_file

log = logging.getLogger(__name__)


_BUCKET = "email-invoices"  # reuse existing bucket; kind separates concerns
_DEFAULT_FILENAME = "Himalayan-Fibres-Price-List.pdf"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _read_bytes(source: str) -> tuple[bytes, str]:
    """Resolve a price-list source to (bytes, content_type).

    - ``http://`` / ``https://`` → fetch via requests
    - anything else → treated as a local filesystem path
    """
    if source.startswith(("http://", "https://")):
        resp = requests.get(source, timeout=15)
        resp.raise_for_status()
        if len(resp.content) > _MAX_BYTES:
            raise ValueError(
                f"Price-list PDF too large: {len(resp.content)} bytes (max {_MAX_BYTES})"
            )
        return resp.content, resp.headers.get("content-type", "application/pdf")

    p = Path(source)
    if not p.exists():
        raise FileNotFoundError(f"Price-list source not found: {source}")
    if p.stat().st_size > _MAX_BYTES:
        raise ValueError(
            f"Price-list PDF too large: {p.stat().st_size} bytes (max {_MAX_BYTES})"
        )
    return p.read_bytes(), "application/pdf"


def attach_current_price_list(
    db,
    *,
    campaign_id: int,
    contact_ids: Iterable[str],
    source: str,
    file_name: str = _DEFAULT_FILENAME,
) -> int:
    """Attach the current price-list PDF to every contact in a campaign.

    Reads ``source`` once, then uploads a per-recipient copy to
    ``email-invoices/price_lists/{campaign_id}/{contact_id}.pdf``.
    Inserts one ``EmailAttachment(kind='price_list')`` row per contact.

    Idempotent on (campaign_id, contact_id, kind) — re-running for the
    same campaign upserts URLs but does not duplicate rows.

    Returns the number of rows written/refreshed.
    """
    contact_ids = list(contact_ids)
    if not contact_ids:
        return 0

    pdf_bytes, content_type = _read_bytes(source)
    log.info(
        "Attaching price list to %d contacts on campaign %s (%d bytes)",
        len(contact_ids), campaign_id, len(pdf_bytes),
    )

    # Look up existing rows once to avoid N selects.
    existing = {
        r.contact_id: r
        for r in db.query(EmailAttachment)
        .filter(
            EmailAttachment.campaign_id == campaign_id,
            EmailAttachment.kind == "price_list",
        )
        .all()
    }

    written = 0
    for cid in contact_ids:
        path = f"price_lists/{campaign_id}/{cid}.pdf"
        signed_url = upload_file(_BUCKET, path, pdf_bytes, content_type=content_type)

        row = existing.get(cid)
        if row is None:
            row = EmailAttachment(
                campaign_id=campaign_id,
                contact_id=cid,
                kind="price_list",
                file_name=file_name,
                storage_bucket=_BUCKET,
                storage_path=path,
                signed_url=signed_url,
                content_type=content_type,
                size_bytes=len(pdf_bytes),
            )
            db.add(row)
        else:
            row.signed_url = signed_url
            row.file_name = file_name
            row.storage_path = path
            row.content_type = content_type
            row.size_bytes = len(pdf_bytes)
        written += 1

    db.commit()
    return written
