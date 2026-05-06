"""Consolidate duplicate (name, language) WATemplate rows (Phase 9.2).

Some templates accumulated multiple rows with the same (name, language)
because the draft-then-Meta-submit flow occasionally created a fresh
APPROVED row instead of updating the existing draft. The Sync-from-Meta
endpoint then crashed with `MultipleResultsFound` because its lookup
used `.one_or_none()`.

Phase 9.2's code fix tolerates duplicates at sync time. This script
cleans up the existing data so the next sync stays clean and the new
sync helpers don't need to keep re-deduping forever.

Rules (cover the ≥3 row case, not just 2):
  1. Group rows by (name, language).
  2. Keeper = highest-id non-draft row. If no non-draft exists in the
     group, keep the highest-id draft.
  3. Field merge: copy `meta_template_id`, `submitted_at`,
     `rejection_reason` from any loser into the keeper if the keeper's
     value is empty/null. Keeper wins on conflict.
  4. Delete losers (with a per-row warning log).
  5. Idempotent — no duplicates → no-op.

Defaults to `--dry-run`. Pass `--confirm` to actually mutate.

Usage:
    python scripts/migrations/2026_05_07_dedup_wa_templates.py            # dry-run
    python scripts/migrations/2026_05_07_dedup_wa_templates.py --confirm  # apply
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
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


def _pick_keeper(rows: list[WATemplate]) -> WATemplate:
    """Highest-id non-draft wins; if none, highest-id draft."""
    non_drafts = [r for r in rows if not r.is_draft]
    pool = non_drafts or rows
    return max(pool, key=lambda r: r.id)


def _merge_into_keeper(keeper: WATemplate, loser: WATemplate) -> list[str]:
    """Copy mergeable fields from loser→keeper if keeper's value is empty.
    Returns a list of field names that were copied (for logging)."""
    copied: list[str] = []
    mergeable = ["meta_template_id", "submitted_at", "rejection_reason"]
    for field in mergeable:
        keeper_val = getattr(keeper, field, None)
        loser_val = getattr(loser, field, None)
        if not keeper_val and loser_val:
            setattr(keeper, field, loser_val)
            copied.append(field)
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Apply changes. Without this flag the script only prints what it would do.",
    )
    args = parser.parse_args(argv)

    db = get_db()
    try:
        rows = db.query(WATemplate).order_by(WATemplate.id.asc()).all()
        groups: dict[tuple[str, str], list[WATemplate]] = defaultdict(list)
        for r in rows:
            groups[(r.name, r.language)].append(r)

        scanned = len(rows)
        groups_with_dupes = 0
        deleted = 0
        merged_fields = 0

        for (name, language), members in groups.items():
            if len(members) < 2:
                continue
            groups_with_dupes += 1
            keeper = _pick_keeper(members)
            losers = [m for m in members if m.id != keeper.id]
            print(
                f"GROUP name={name!r} language={language!r} "
                f"members={len(members)} keeper_id={keeper.id} "
                f"keeper_is_draft={keeper.is_draft}"
            )
            for loser in losers:
                copied = _merge_into_keeper(keeper, loser)
                merged_fields += len(copied)
                print(
                    f"  - delete id={loser.id} is_draft={loser.is_draft}"
                    + (f" merged_fields={copied}" if copied else "")
                )
                if args.confirm:
                    db.delete(loser)
                deleted += 1

        if args.confirm:
            db.commit()
            mode = "APPLIED"
        else:
            db.rollback()
            mode = "DRY-RUN (no changes; pass --confirm to apply)"

        print(
            f"\n{mode}\n"
            f"scanned={scanned} "
            f"groups_with_dupes={groups_with_dupes} "
            f"would_delete={deleted} "
            f"would_merge_fields={merged_fields}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
