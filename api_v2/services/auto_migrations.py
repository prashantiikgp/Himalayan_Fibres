"""Idempotent schema-fix runner — applied at api_v2 startup.

Plan D + STANDARDS §2 says additive ALTERs (`ADD COLUMN nullable`) are
safe to run automatically against the prod DB. Anything riskier
(DROP / RENAME / NOT NULL backfills) lives in scripts/migrations/ and
must be invoked manually.

This module checks the live DB for known-missing additive columns and
runs the ALTER at startup. Safe to call repeatedly — every fix is
gated behind an `inspect()` check.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

log = logging.getLogger("api_v2.auto_migrations")


def _column_exists(engine, table: str, column: str) -> bool:  # type: ignore[no-untyped-def]
    insp = inspect(engine)
    try:
        cols = {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return False
    return column in cols


def _add_column(engine, table: str, column: str, ddl_type: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    """Add a nullable column. `ddl_type` maps dialect_name → SQL type."""
    if _column_exists(engine, table, column):
        return
    type_sql = ddl_type.get(engine.dialect.name) or ddl_type.get("default", "TIMESTAMP NULL")
    sql = f"ALTER TABLE {table} ADD COLUMN {column} {type_sql}"
    log.info("auto-migration: %s", sql)
    with engine.begin() as conn:
        conn.execute(text(sql))


def run_all() -> None:
    """Apply every known additive fix. Called from api_v2/main.py."""
    from services.database import get_engine  # type: ignore[import-not-found]

    engine = get_engine()
    try:
        # Phase 3.1b.2 — Broadcast.scheduled_at
        _add_column(
            engine,
            table="broadcasts",
            column="scheduled_at",
            ddl_type={
                "postgresql": "TIMESTAMP WITH TIME ZONE",
                "sqlite": "DATETIME",
                "default": "TIMESTAMP NULL",
            },
        )
    except Exception:
        log.exception("auto-migration failed; continuing without it")
