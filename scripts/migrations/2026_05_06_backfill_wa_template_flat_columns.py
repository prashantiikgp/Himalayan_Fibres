"""Backfill WATemplate flat columns from `components` (Phase 7.4).

Before Phase 7.4, `WhatsAppSender.sync_templates_from_meta` wrote Meta's
raw `components` JSON to `WATemplate.components` but never decomposed it
into the flat columns (`body_text`, `header_text`, etc.) the dashboard
reads from. This script runs the new `decompose_components` over every
existing row whose flat columns are empty, so operators don't need to
re-hit Meta with a fresh sync to get a usable preview.

Idempotent: rows whose flat columns are already non-empty are left
alone. Safe to re-run.

Usage:
    python scripts/migrations/2026_05_06_backfill_wa_template_flat_columns.py

Run **once** after deploying the Phase 7.4 backend. From that point on,
every `Sync from Meta` action will keep flat columns in sync via the
new code path; this script is one-shot insurance for the existing rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HF_DASHBOARD = REPO_ROOT / "hf_dashboard"
if str(HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(HF_DASHBOARD))

try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from services.database import get_db  # type: ignore[import-not-found]  # noqa: E402
from services.models import WATemplate  # type: ignore[import-not-found]  # noqa: E402
from services.wa_template_builder import decompose_components  # type: ignore[import-not-found]  # noqa: E402


def main() -> int:
    db = get_db()
    try:
        rows = db.query(WATemplate).all()
        scanned = 0
        backfilled = 0
        skipped_no_components = 0
        skipped_already_filled = 0

        for t in rows:
            scanned += 1
            components = t.components or []
            if not components:
                skipped_no_components += 1
                continue
            # Idempotency guard: if body_text is already set, treat the row
            # as already-decomposed. (body_text is the load-bearing flat
            # column — every non-empty Meta template has a BODY component.)
            if (t.body_text or "").strip():
                skipped_already_filled += 1
                continue

            flat = decompose_components(components)
            t.body_text = flat["body_text"]
            t.header_format = flat["header_format"]
            t.header_text = flat["header_text"]
            t.header_asset_url = flat["header_asset_url"]
            t.footer_text = flat["footer_text"]
            t.buttons = flat["buttons"]
            backfilled += 1

        db.commit()
        print(
            f"scanned={scanned} backfilled={backfilled} "
            f"skipped_no_components={skipped_no_components} "
            f"skipped_already_filled={skipped_already_filled}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
