#!/usr/bin/env python
"""Phase A smoke test for the Jinja2 email template system.

Runs against a TEMPORARY SQLite database (not the real dev DB) so it's
safe to run multiple times without polluting state.

Verifies:
  1. All 5 seed templates (welcome, order_confirmation, order_shipped,
     order_delivered_feedback, operational_update) are seeded with
     metadata rows in email_templates.
  2. Every template renders successfully via render_template_by_slug
     with full shared-config + per-recipient vars in one pass.
  3. The locked shell (banner URL, footer address, Amiri font, social
     icons) appears in every rendered output.
  4. order_confirmation with invoice_url set renders a ``Download
     Invoice`` button.
  5. order_confirmation with empty invoice_url HIDES that button via
     the ``{% if invoice_url %}`` guard.
  6. Idempotent reseed: re-running skips existing rows.

Usage::

    python scripts/smoke_test_email_templates.py
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

# Force SQLite fallback before any service imports.
os.environ.pop("DATABASE_URL", None)
_TMP_DB = Path(tempfile.mkdtemp(prefix="hf_smoke_")) / "smoke.db"
os.environ["SQLITE_PATH"] = str(_TMP_DB)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hf_dashboard"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from services.database import get_db, init_db  # noqa: E402
from services.email_sender import render_template_by_slug  # noqa: E402
from services.email_shared_config import load_shared_config  # noqa: E402
from services.models import EmailTemplate  # noqa: E402
from services.template_seed import seed_email_templates  # noqa: E402


EXPECTED_SLUGS = {
    "welcome",
    "order_confirmation",
    "order_shipped",
    "order_delivered_feedback",
    "operational_update",
}


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        raise SystemExit(1)
    print(f"  ✓ {msg}")


def _base_vars(overrides: dict | None = None) -> dict:
    """Shared config + per-recipient defaults + caller overrides."""
    base = dict(load_shared_config())
    base.update(
        {
            "first_name": "Alisha",
            "last_name": "Panda",
            "name": "Alisha Panda",
            "email": "alisha@example.com",
            "company_name_contact": "",
            "invoice_url": "",
        }
    )
    if overrides:
        base.update(overrides)
    return base


def main() -> int:
    print(f"Using temp SQLite: {_TMP_DB}")
    init_db()
    db = get_db()
    try:
        summary = seed_email_templates(db, force=True)
        print(f"Seed summary: {summary}")

        # ── Step 1: all 5 slugs present in DB ─────────────────────
        rows = db.query(EmailTemplate).filter(EmailTemplate.slug.in_(EXPECTED_SLUGS)).all()
        _assert(
            {r.slug for r in rows} == EXPECTED_SLUGS,
            f"all 5 seed slugs present (got: {sorted(r.slug for r in rows)})",
        )

        # ── Step 2 + 3: each template renders + has locked shell ──
        for slug in sorted(EXPECTED_SLUGS):
            vars_for_slug = _base_vars()
            if slug == "order_confirmation":
                vars_for_slug.update(
                    order_number="10014",
                    order_date="30-Aug-2025",
                    items_html="<p>Himalayan Woollen Yarn × 500g</p>",
                    subtotal="Rs 750",
                    shipping="Rs 200",
                    total="Rs 950",
                    payment_method="UPI",
                )
            elif slug == "order_shipped":
                vars_for_slug.update(
                    courier_name="BlueDart",
                    tracking_id="BD123456789",
                    dispatch_date="01-Sep-2025",
                    delivery_date="05-Sep-2025",
                    tracking_url="https://www.bluedart.com/track/BD123456789",
                )
            elif slug == "operational_update":
                vars_for_slug.update(
                    update_title="Payment Gateway Activated",
                    update_body_html="<p>Our payment gateway is now live. Try placing your order again.</p>",
                )

            html = render_template_by_slug(slug, vars_for_slug)
            _assert(len(html) > 500, f"{slug}: non-empty rendered output")
            _assert("supabase.co" in html, f"{slug}: banner URL rendered (shell locked)")
            _assert("S.K. Complex" in html, f"{slug}: footer address rendered (shell locked)")
            _assert("Privacy Policy" in html, f"{slug}: footer policy links rendered (shell locked)")
            _assert("Amiri" in html, f"{slug}: Amiri font-stack present")
            _assert("icons8.com" in html, f"{slug}: social icons rendered (shell locked)")

        # ── Step 4: invoice button SHOWN when invoice_url set ─────
        with_invoice = render_template_by_slug(
            "order_confirmation",
            _base_vars(
                {
                    "invoice_url": "https://example.com/invoice-10014.pdf",
                    "order_number": "10014",
                    "order_date": "30-Aug-2025",
                    "items_html": "<p>Yarn × 500g</p>",
                    "total": "Rs 950",
                }
            ),
        )
        _assert("Alisha" in with_invoice, "order_confirmation: first_name substituted")
        _assert(
            "https://example.com/invoice-10014.pdf" in with_invoice,
            "order_confirmation: invoice_url substituted into button href",
        )
        _assert(
            "Download Invoice" in with_invoice,
            "order_confirmation: Download Invoice button rendered when invoice_url set",
        )

        # ── Step 5: invoice button HIDDEN when invoice_url empty ──
        no_invoice = render_template_by_slug(
            "order_confirmation",
            _base_vars(
                {
                    "invoice_url": "",
                    "order_number": "10014",
                    "order_date": "30-Aug-2025",
                    "items_html": "<p>Yarn × 500g</p>",
                    "total": "Rs 950",
                }
            ),
        )
        _assert(
            "Download Invoice" not in no_invoice,
            "order_confirmation: Download Invoice button HIDDEN when invoice_url empty",
        )

        # ── Step 6: idempotent second seed ────────────────────────
        second = seed_email_templates(db, force=False)
        _assert(
            second["inserted"] == 0,
            f"second seed inserted=0 (got inserted={second['inserted']})",
        )
        _assert(
            second["skipped"] >= 5,
            f"second seed skipped>=5 (got skipped={second['skipped']})",
        )

        print()
        print("ALL PASSED ✓")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
