#!/usr/bin/env python
"""Phase B smoke test — EmailAttachment model + personalization helper.

Does NOT hit Supabase Storage (storage3 is tested in Phase C integration
via the live Space). This test only verifies the DB model + helper +
render pipeline works end-to-end:

  1. EmailAttachment table is created by create_all (no migration needed).
  2. Inserting a fake EmailAttachment row with a signed_url placeholder
     lets build_send_variables surface it as `invoice_url`.
  3. Rendering order_confirmation with those vars produces the
     Download Invoice button with the right href.
  4. Dropping the attachment row makes `invoice_url` empty → button hides.
  5. load_campaign_attachments does a single query regardless of N
     recipients (verified by queries-count assertion via SQLAlchemy event).

Usage::

    python scripts/smoke_test_phase_b.py
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

os.environ.pop("DATABASE_URL", None)
_TMP_DB = Path(tempfile.mkdtemp(prefix="hf_smoke_b_")) / "smoke.db"
os.environ["SQLITE_PATH"] = str(_TMP_DB)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hf_dashboard"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from sqlalchemy import event  # noqa: E402

from services.database import get_db, get_engine, init_db  # noqa: E402
from services.email_personalization import (  # noqa: E402
    build_send_variables,
    load_campaign_attachments,
)
from services.email_sender import render_template_by_slug  # noqa: E402
from services.models import Campaign, Contact, EmailAttachment  # noqa: E402
from services.template_seed import seed_email_templates  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        raise SystemExit(1)
    print(f"  ✓ {msg}")


def main() -> int:
    print(f"Using temp SQLite: {_TMP_DB}")
    init_db()

    # Make sure the new EmailAttachment table was actually created.
    engine = get_engine()
    with engine.connect() as conn:
        from sqlalchemy import text as sql_text
        result = conn.execute(
            sql_text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='email_attachments'"
            )
        ).fetchone()
        _assert(
            result is not None,
            "email_attachments table created by create_all",
        )

    db = get_db()
    try:
        # Seed templates so we can render order_confirmation later
        seed_email_templates(db, force=True)

        # Create a Campaign + two Contacts
        campaign = Campaign(name="Test Campaign", subject="Test", status="draft")
        db.add(campaign)
        db.flush()

        contact_with = Contact(
            id="c1",
            email="alisha@example.com",
            first_name="Alisha",
            last_name="Panda",
        )
        contact_without = Contact(
            id="c2",
            email="ravi@example.com",
            first_name="Ravi",
            last_name="Kumar",
        )
        db.add_all([contact_with, contact_without])
        db.flush()

        # Attach a fake invoice for contact c1 only
        att = EmailAttachment(
            campaign_id=campaign.id,
            contact_id="c1",
            kind="invoice",
            file_name="invoice-10014.pdf",
            storage_bucket="email-invoices",
            storage_path=f"campaign_{campaign.id}/contact_c1/invoice-10014.pdf",
            signed_url="https://yxlofrkkzjkxtbowyryj.supabase.co/storage/v1/object/sign/email-invoices/test?token=fake",
            content_type="application/pdf",
            size_bytes=12345,
        )
        db.add(att)
        db.commit()

        # ── Count queries when loading attachments ───────────────
        query_counter = {"n": 0}

        @event.listens_for(engine, "before_cursor_execute")
        def _count(conn, cursor, statement, parameters, context, executemany):
            if "email_attachments" in statement.lower():
                query_counter["n"] += 1

        attachments = load_campaign_attachments(db, campaign.id)
        _assert(
            query_counter["n"] == 1,
            f"load_campaign_attachments does exactly 1 DB query (got {query_counter['n']})",
        )
        _assert(
            "c1" in attachments and "c2" not in attachments,
            "attachments dict keyed by contact_id with c1 present, c2 absent",
        )

        # ── build_send_variables for recipient with attachment ───
        vars_c1 = build_send_variables(
            contact_with,
            attachments,
            extra={
                "order_number": "10014",
                "order_date": "30-Aug-2025",
                "items_html": "<p>Himalayan Woollen Yarn × 500g</p>",
                "total": "Rs 950",
            },
        )
        _assert(
            vars_c1["first_name"] == "Alisha",
            "build_send_variables surfaces contact.first_name",
        )
        _assert(
            vars_c1["invoice_url"].startswith("https://yxlofrkkzjkxtbowyryj"),
            "build_send_variables surfaces invoice_url from attachment",
        )
        _assert(
            "banner_url" in vars_c1 and vars_c1["banner_url"],
            "build_send_variables merges shared branding config (banner_url present)",
        )

        html_c1 = render_template_by_slug("order_confirmation", vars_c1)
        _assert("Download Invoice" in html_c1, "recipient with attachment: button rendered")
        _assert(
            vars_c1["invoice_url"] in html_c1,
            "recipient with attachment: invoice_url injected into href",
        )
        _assert("Alisha" in html_c1, "recipient with attachment: first_name rendered")

        # ── build_send_variables for recipient WITHOUT attachment ─
        vars_c2 = build_send_variables(
            contact_without,
            attachments,
            extra={
                "order_number": "10015",
                "order_date": "30-Aug-2025",
                "items_html": "<p>Himalayan Hemp × 500g</p>",
                "total": "Rs 800",
            },
        )
        _assert(
            vars_c2["invoice_url"] == "",
            "build_send_variables returns empty invoice_url when no attachment",
        )

        html_c2 = render_template_by_slug("order_confirmation", vars_c2)
        _assert(
            "Download Invoice" not in html_c2,
            "recipient without attachment: button HIDDEN",
        )
        _assert("Ravi" in html_c2, "recipient without attachment: first_name rendered")

        # ── Same two renders with DRAFT campaign (campaign_id=None) ──
        draft_atts = load_campaign_attachments(db, None)
        _assert(
            draft_atts == {},
            "load_campaign_attachments returns {} for None campaign_id",
        )

        print()
        print("ALL PASSED ✓")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
