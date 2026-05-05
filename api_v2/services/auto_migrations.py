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


def run_all() -> dict:
    """Apply every known additive fix. Called from api_v2/main.py.

    Returns a dict of {column_path: status} where status is one of
    "ok" / "already_present" / "failed:<reason>". Caller logs this and
    surfaces failures (review fix #5: was silent before)."""
    from services.database import get_engine  # type: ignore[import-not-found]

    engine = get_engine()
    results: dict[str, str] = {}

    fixes = [
        # Phase 3.1b.2 — Broadcast.scheduled_at
        {
            "path": "broadcasts.scheduled_at",
            "table": "broadcasts",
            "column": "scheduled_at",
            "ddl_type": {
                "postgresql": "TIMESTAMP WITH TIME ZONE",
                "sqlite": "DATETIME",
                "default": "TIMESTAMP NULL",
            },
        },
        # Phase 7.7 — Flow trigger model + slug
        {
            "path": "flows.slug",
            "table": "flows",
            "column": "slug",
            "ddl_type": {
                "postgresql": "VARCHAR(64)",
                "sqlite": "VARCHAR(64)",
                "default": "VARCHAR(64) NULL",
            },
        },
        {
            "path": "flows.trigger_type",
            "table": "flows",
            "column": "trigger_type",
            "ddl_type": {
                "postgresql": "VARCHAR(32) NOT NULL DEFAULT 'manual'",
                "sqlite": "VARCHAR(32) NOT NULL DEFAULT 'manual'",
                "default": "VARCHAR(32) NOT NULL DEFAULT 'manual'",
            },
        },
        {
            "path": "flows.trigger_config",
            "table": "flows",
            "column": "trigger_config",
            "ddl_type": {
                "postgresql": "JSONB DEFAULT '{}'::jsonb",
                "sqlite": "TEXT",
                "default": "TEXT",
            },
        },
        {
            "path": "flows.updated_at",
            "table": "flows",
            "column": "updated_at",
            "ddl_type": {
                "postgresql": "TIMESTAMP WITH TIME ZONE",
                "sqlite": "DATETIME",
                "default": "TIMESTAMP NULL",
            },
        },
        # Phase 7.2b — Campaign.variables (typed compose-time vars carried
        # through schedule-and-fire). Defaults to empty JSON so existing
        # rows are backfilled implicitly; the engine treats {} as "no
        # extra vars" and just resolves the per-recipient ones.
        {
            "path": "campaigns.variables",
            "table": "campaigns",
            "column": "variables",
            "ddl_type": {
                "postgresql": "JSONB DEFAULT '{}'::jsonb",
                "sqlite": "TEXT DEFAULT '{}'",
                "default": "TEXT",
            },
        },
    ]

    for fix in fixes:
        path = str(fix["path"])
        try:
            if _column_exists(engine, str(fix["table"]), str(fix["column"])):
                results[path] = "already_present"
                continue
            _add_column(engine, fix["table"], fix["column"], fix["ddl_type"])  # type: ignore[arg-type]
            results[path] = "ok"
        except Exception as e:
            results[path] = f"failed:{e!s}"
            log.exception("auto-migration %s failed", path)
            # Review fix #5: forward to Sentry so the team sees it
            # even when nobody's tailing logs.
            try:
                import sentry_sdk  # type: ignore[import-not-found]

                sentry_sdk.capture_exception(e)
            except ImportError:
                pass

    return results


def required_columns_present() -> tuple[bool, list[str]]:
    """Check whether the columns the scheduler depends on actually
    exist in the live DB. Returns (all_present, missing_paths)."""
    from services.database import get_engine  # type: ignore[import-not-found]

    engine = get_engine()
    required = [
        ("broadcasts", "scheduled_at"),
        ("flows", "trigger_type"),
        ("flows", "trigger_config"),
    ]
    missing = [
        f"{t}.{c}" for t, c in required if not _column_exists(engine, t, c)
    ]
    return (not missing, missing)
