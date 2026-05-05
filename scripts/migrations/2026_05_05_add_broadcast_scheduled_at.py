"""Add `scheduled_at` to the `broadcasts` table.

Phase 3.1b.2 schema migration. The `campaigns` table already has this
column; only WA broadcasts (the `broadcasts` table) need it added.

Idempotent: checks information_schema (Postgres) or PRAGMA (SQLite)
before issuing the ALTER. Safe to run multiple times.

Usage:
    python scripts/migrations/2026_05_05_add_broadcast_scheduled_at.py

Run **before** the v2 Phase 3.1b.2 deploy that depends on this column.
v1 keeps working unchanged — the column is unused by v1 today.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HF_DASHBOARD = REPO_ROOT / "hf_dashboard"
if str(HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(HF_DASHBOARD))

# load .env from the repo root so DATABASE_URL is available
try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from sqlalchemy import inspect, text  # noqa: E402

from services.database import get_engine  # type: ignore[import-not-found]

engine = get_engine()


TABLE = "broadcasts"
COLUMN = "scheduled_at"


def column_exists() -> bool:
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns(TABLE)}
    return COLUMN in cols


def main() -> int:
    if column_exists():
        print(f"✓ {TABLE}.{COLUMN} already exists — nothing to do")
        return 0

    dialect = engine.dialect.name
    if dialect == "postgresql":
        ddl = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TIMESTAMP WITH TIME ZONE"
    elif dialect == "sqlite":
        ddl = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} DATETIME"
    else:
        # Default ANSI; SQLAlchemy's compiler will translate.
        ddl = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} TIMESTAMP NULL"

    print(f"Running on {dialect}: {ddl}")
    with engine.begin() as conn:
        conn.execute(text(ddl))

    if column_exists():
        print(f"✓ Added {TABLE}.{COLUMN}")
        return 0
    print(f"✗ Column not visible after ALTER — investigate", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
