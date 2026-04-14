#!/usr/bin/env python
"""Reseed the email_templates table from hf_dashboard/config/email/templates_seed/.

Default run seeds any missing slugs (idempotent, non-destructive).

Pass --force to UPDATE existing rows' html_content, subject_template,
name, category, and required_variables from disk. The ``is_active``
flag is never overwritten, so a disabled template stays disabled.

Usage
-----

    # Seed new templates, leave existing ones alone
    python scripts/reseed_email_templates.py

    # Force-rebuild every seeded template from disk
    python scripts/reseed_email_templates.py --force
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make hf_dashboard imports work when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hf_dashboard"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from services.database import get_db, init_db  # noqa: E402
from services.template_seed import seed_email_templates  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Reseed email templates from disk")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing rows' html_content and metadata (is_active preserved).",
    )
    args = parser.parse_args()

    init_db()
    db = get_db()
    try:
        summary = seed_email_templates(db, force=args.force)
    finally:
        db.close()

    print(f"Summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
