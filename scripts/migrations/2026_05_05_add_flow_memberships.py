"""Phase 7.7 schema finalization — last gaps on the flow trigger model.

Most of the schema (Flow.slug, Flow.trigger_type, Flow.trigger_config,
Flow.updated_at; flow_memberships; flow_step_runs) was shipped in
earlier work. This script closes the remaining structural gaps from
PLAN_flows §3.1.2:

  1. Backfill any null `flows.slug` values from `lower(replace(name, ' ', '_'))`.
  2. UNIQUE index on `flows(slug)`.
  3. Partial unique index on `flow_memberships(contact_id, flow_id)`
     WHERE status IN ('active', 'waiting_event', 'paused').
     This is the structural defence against duplicate enrollment;
     without it, the §4.5 idempotency claim is just an app-level check
     that races under concurrent triggers (Postgres only — SQLite uses
     a pre-insert SELECT in the engine code as a softer fallback).

Also serves as a safety net for fresh installs: ensures
`flow_memberships` and `flow_step_runs` exist (a no-op if `create_all`
already made them on first boot of `ensure_db_ready`). Idempotent
throughout — every step is gated by an inspector check.

Usage::

    python scripts/migrations/2026_05_05_add_flow_memberships.py

Run before deploying api_v2 with the Phase 7.7 flows engine.
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
from services.models import Base, FlowMembership, FlowStepRun  # type: ignore[import-not-found]  # noqa: F401

engine = get_engine()


def _table_exists(table: str) -> bool:
    return table in inspect(engine).get_table_names()


def _index_names(table: str) -> set[str]:
    insp = inspect(engine)
    try:
        return {idx["name"] for idx in insp.get_indexes(table)}
    except Exception:
        return set()


def _backfill_flow_slugs() -> int:
    """Populate flows.slug for any rows that don't have one yet.

    Used by the seed flows shipped in v1 — they were inserted before
    the slug column existed, so even after the additive ALTER they
    have NULL slugs.
    """
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, name FROM flows WHERE slug IS NULL OR slug = ''")
        ).fetchall()
        n = 0
        for row in rows:
            flow_id, name = row[0], (row[1] or f"flow_{row[0]}")
            slug_base = name.strip().lower()
            for ch in [" ", "/", "—", "-"]:
                slug_base = slug_base.replace(ch, "_")
            slug_base = "".join(c for c in slug_base if c.isalnum() or c == "_")[:64] or f"flow_{flow_id}"
            slug = slug_base
            i = 1
            while conn.execute(
                text("SELECT 1 FROM flows WHERE slug = :s AND id <> :i"),
                {"s": slug, "i": flow_id},
            ).first():
                i += 1
                slug = f"{slug_base}_{i}"
            conn.execute(
                text("UPDATE flows SET slug = :s WHERE id = :i"),
                {"s": slug, "i": flow_id},
            )
            n += 1
    return n


def _create_unique_index_on_slug() -> str:
    if "flows_slug_uniq" in _index_names("flows"):
        return "already_present"
    sql = "CREATE UNIQUE INDEX IF NOT EXISTS flows_slug_uniq ON flows(slug)"
    print(f"  -> {sql}")
    with engine.begin() as conn:
        conn.execute(text(sql))
    return "ok"


def _create_fm_contact_flow_uniq() -> str:
    """Add the partial unique index on (contact_id, flow_id) for live memberships.

    This is the structural guarantee from PLAN_flows §3.4 / §4.5 —
    without it, two concurrent tag-trigger evaluators racing on the
    same contact would both see "no active membership" and both insert.

    Postgres supports partial indexes natively. SQLite does too (since
    3.8.0), so the same DDL works on dev. The engine's pre-insert
    SELECT remains as a defence in depth.
    """
    if "fm_contact_flow_uniq" in _index_names("flow_memberships"):
        return "already_present"
    sql = (
        "CREATE UNIQUE INDEX IF NOT EXISTS fm_contact_flow_uniq "
        "ON flow_memberships(contact_id, flow_id) "
        "WHERE status IN ('active', 'waiting_event', 'paused')"
    )
    print(f"  -> {sql}")
    with engine.begin() as conn:
        conn.execute(text(sql))
    return "ok"


def main() -> int:
    print(f"Phase 7.7 schema finalization on {engine.dialect.name}")

    print("[1/4] safety-net create flow_memberships + flow_step_runs (if missing)")
    Base.metadata.create_all(
        engine,
        tables=[
            FlowMembership.__table__,
            FlowStepRun.__table__,
        ],
    )

    print("[2/4] backfill flows.slug")
    n = _backfill_flow_slugs()
    print(f"  -> backfilled {n} rows")

    print("[3/4] flows_slug_uniq index")
    _create_unique_index_on_slug()

    print("[4/4] fm_contact_flow_uniq partial index")
    _create_fm_contact_flow_uniq()

    print("✓ Phase 7.7 schema finalization complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
