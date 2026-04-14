"""Idempotent migration: add draft-specific columns to wa_templates and product_media.

Why this exists: hf_dashboard/services/database.py::init_db calls
`Base.metadata.create_all`, which creates missing tables but never ALTERs
existing ones. Once `wa_templates` and `product_media` exist on the live HF
Space DB (they do), adding new columns to the SQLAlchemy models has zero
effect on the actual schema — queries will then crash with
`UndefinedColumn`. This script bridges that gap.

Run order on HF Spaces: deploy new code → run this script against the live
DB → restart Space. On a brand-new DB the script is still safe: it detects
missing columns, adds only those, and exits cleanly.

Safe to re-run. Each ALTER is gated by an existence check against
information_schema (Postgres) or PRAGMA table_info (SQLite), so a second
invocation does nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hf_dashboard"))

from sqlalchemy import text
from sqlalchemy.engine import Engine

from services.database import get_engine


WA_TEMPLATE_COLUMNS: list[tuple[str, str, str]] = [
    # (column_name, postgres_type, sqlite_type)
    ("is_draft", "BOOLEAN NOT NULL DEFAULT FALSE", "BOOLEAN NOT NULL DEFAULT 0"),
    ("body_text", "TEXT NOT NULL DEFAULT ''", "TEXT NOT NULL DEFAULT ''"),
    ("header_format", "VARCHAR(20)", "VARCHAR(20)"),
    ("header_asset_url", "VARCHAR(512)", "VARCHAR(512)"),
    ("header_text", "VARCHAR(60)", "VARCHAR(60)"),
    ("footer_text", "VARCHAR(60)", "VARCHAR(60)"),
    ("buttons", "JSONB NOT NULL DEFAULT '[]'::jsonb", "TEXT NOT NULL DEFAULT '[]'"),
    ("variables", "JSONB NOT NULL DEFAULT '[]'::jsonb", "TEXT NOT NULL DEFAULT '[]'"),
    ("rejection_reason", "TEXT NOT NULL DEFAULT ''", "TEXT NOT NULL DEFAULT ''"),
    ("submitted_at", "TIMESTAMP WITH TIME ZONE", "DATETIME"),
    ("meta_template_id", "VARCHAR(64)", "VARCHAR(64)"),
]

PRODUCT_MEDIA_COLUMNS: list[tuple[str, str, str]] = [
    ("kind", "VARCHAR(32) NOT NULL DEFAULT 'product'", "VARCHAR(32) NOT NULL DEFAULT 'product'"),
    ("public_url", "VARCHAR(512)", "VARCHAR(512)"),
]


def _existing_columns(engine: Engine, table: str) -> set[str]:
    dialect = engine.dialect.name
    with engine.connect() as conn:
        if dialect == "postgresql":
            rows = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t"
                ),
                {"t": table},
            ).fetchall()
            return {r[0] for r in rows}
        if dialect == "sqlite":
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            return {r[1] for r in rows}
    raise RuntimeError(f"Unsupported dialect: {dialect}")


def _add_missing(engine: Engine, table: str, columns: list[tuple[str, str, str]]) -> list[str]:
    dialect = engine.dialect.name
    existing = _existing_columns(engine, table)
    if not existing:
        print(f"  ⚠ table `{table}` does not exist yet — create_all will handle it on next startup")
        return []

    added: list[str] = []
    with engine.begin() as conn:
        for name, pg_type, sqlite_type in columns:
            if name in existing:
                continue
            col_type = pg_type if dialect == "postgresql" else sqlite_type
            stmt = f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"
            print(f"  + {stmt}")
            conn.execute(text(stmt))
            added.append(name)
    return added


def main() -> int:
    engine = get_engine()
    print(f"Migrating against: {engine.dialect.name}")

    print("wa_templates:")
    added_tpl = _add_missing(engine, "wa_templates", WA_TEMPLATE_COLUMNS)
    if not added_tpl:
        print("  (no changes)")

    print("product_media:")
    added_pm = _add_missing(engine, "product_media", PRODUCT_MEDIA_COLUMNS)
    if not added_pm:
        print("  (no changes)")

    total = len(added_tpl) + len(added_pm)
    print(f"\nDone. Added {total} column(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
