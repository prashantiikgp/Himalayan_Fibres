"""Add `variables` JSON column to the `campaigns` table.

Phase 7.2b schema migration. Lets scheduled email broadcasts persist
the typed variable values from the Compose form across the
schedule-and-fire boundary — without this column, scheduled broadcasts
would silently fall back to `{}` and miss the user's typed CTA / dates
/ IDs.

Idempotent: checks information_schema (Postgres) or PRAGMA (SQLite)
before issuing the ALTER. Safe to re-run.

Usage:
    python scripts/migrations/2026_05_07_add_campaign_variables_column.py

Auto-applied at api_v2 startup via `api_v2/services/auto_migrations.py`,
so on the HF Space this script normally doesn't need to run by hand —
it's kept as the documented escape hatch for environments that disable
auto-migrations.
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

from sqlalchemy import inspect, text  # noqa: E402

from services.database import get_engine  # type: ignore[import-not-found]


TABLE = "campaigns"
COLUMN = "variables"


def column_exists(engine) -> bool:  # type: ignore[no-untyped-def]
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns(TABLE)}
    return COLUMN in cols


def main() -> int:
    engine = get_engine()
    if column_exists(engine):
        print(f"✓ {TABLE}.{COLUMN} already exists — nothing to do")
        return 0

    dialect = engine.dialect.name
    if dialect == "postgresql":
        ddl = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} JSONB DEFAULT '{{}}'::jsonb"
    elif dialect == "sqlite":
        ddl = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TEXT DEFAULT '{{}}'"
    else:
        ddl = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TEXT"

    print(f"Running on {dialect}: {ddl}")
    with engine.begin() as conn:
        conn.execute(text(ddl))

    if column_exists(engine):
        print(f"✓ Added {TABLE}.{COLUMN}")
        return 0
    print("✗ Column not visible after ALTER — investigate", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
