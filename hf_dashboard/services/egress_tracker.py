"""Per-query Supabase egress tracker (Plan D Phase 0).

Attaches a SQLAlchemy `after_cursor_execute` listener to the Postgres
engine and counts rows returned per canonical SELECT fingerprint. Dumps
the rolling counters to `data/egress_log_YYYY-MM-DD.json` (or `/data/`
on HF Spaces) every 100 queries.

Purely diagnostic. Used during Plan D Phase 0 to rank actual DB readers
by measured rows pulled so the Phase 1 fix-up priorities are grounded in
real numbers, not the paper audit.

**This module intentionally ignores SQLite.** Local dev runs against a
file DB where "egress" is not a thing. The installer is a no-op unless
the engine's dialect is postgresql.

**Removal plan.** Delete the `install_egress_tracker(_engine)` call in
`services/database.py::get_engine` once Plan D is shipped and verified.
The tracker itself leaves no schema or data artifacts beyond the JSON
log files; those can be deleted or left in `/data` as a historical
record.

Limitations:
    - `cursor.rowcount` is used as the row-count signal. For psycopg2 +
      SELECT this is populated after execute() but BEFORE the ORM has
      fetched the rows. It is reliable for simple queries but may return
      -1 for server-side cursors or streaming result sets — those are
      skipped (counted as zero, which under-reports rather than over).
    - Bytes are NOT measured directly. We only track row counts per
      fingerprint + one sample of the statement text. A post-processor
      can multiply by a per-table average-row-width table (see
      `scripts/egress_report.py` when it's written) to turn rows into
      byte estimates.
    - No locking on the JSON write path beyond a Python `threading.Lock`.
      If the Space crashes mid-flush the file could be corrupted; next
      flush overwrites it, so the loss is at most ~100 queries worth of
      counters.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

# fingerprint -> {"calls", "rows", "first_seen", "last_seen", "sample"}
_COUNTERS: dict[str, dict] = {}
_LOCK = threading.Lock()
_FLUSH_EVERY = 100
_queries_since_flush = 0
_installed = False

# SQL literal-stripping regex: replaces quoted strings and bare numbers
# with `?` so queries that differ only by parameters group under one
# fingerprint. Intentionally simple — doesn't handle escaped quotes or
# hex literals, but those are rare in our codebase and good-enough
# grouping is what we need here.
_LITERAL_RE = re.compile(r"'(?:[^']|'')*'|\b\d+\b")
_WS_RE = re.compile(r"\s+")
# First FROM clause in the (un-truncated) statement gives us the
# primary table. Matched before we truncate the fingerprint so long
# SELECTs with hundreds of column aliases still get classified.
_FROM_RE = re.compile(r"FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


def _fingerprint(statement: str) -> str:
    """Canonicalise a SQL statement so parameter variants collapse."""
    s = _WS_RE.sub(" ", statement or "").strip()
    s = _LITERAL_RE.sub("?", s)
    return s[:240]


def _extract_table(statement: str) -> str:
    """Return the first FROM-clause table name, or '?' if none found.

    Runs against the full statement (not the truncated fingerprint) so
    wide SELECTs with many column aliases still classify correctly.
    pg_catalog reflection queries return things like `pg_catalog.pg_class`
    — we strip the schema prefix so they group under `pg_class`.
    """
    m = _FROM_RE.search(statement or "")
    if not m:
        return "?"
    name = m.group(1).lower()
    # pg_catalog queries sometimes look like `FROM pg_catalog.pg_class`
    # — the regex matches `pg_catalog`. Skip it and take the next FROM.
    if name == "pg_catalog":
        for m2 in _FROM_RE.finditer(statement or ""):
            candidate = m2.group(1).lower()
            if candidate != "pg_catalog":
                return candidate
    return name


def _log_dir() -> Path:
    """Return the directory to write egress logs into.

    Prefer `/data` (the HF Space persistent volume) when it exists; fall
    back to `hf_dashboard/data/` for local dev. We create the dir if
    missing — the Contact seeder creates `hf_dashboard/data/` on first
    boot anyway.
    """
    if Path("/data").is_dir():
        return Path("/data")
    return Path(__file__).resolve().parent.parent / "data"


def _log_path() -> Path:
    base = _log_dir()
    base.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return base / f"egress_log_{today}.json"


def _flush_locked() -> None:
    """Dump current counters to the daily log. Caller must hold _LOCK."""
    try:
        path = _log_path()
        path.write_text(json.dumps(_COUNTERS, indent=2, sort_keys=True))
    except OSError as e:
        _log.warning("egress_tracker: flush failed: %s", e)


def snapshot() -> dict[str, dict]:
    """Return a deep-ish copy of the current counters.

    Used by the Plan D Phase 0 report script so it can read the in-memory
    state without touching the on-disk log (useful when the flush
    threshold hasn't been reached yet).
    """
    with _LOCK:
        return {fp: dict(v) for fp, v in _COUNTERS.items()}


def install_egress_tracker(engine: Engine) -> None:
    """Attach the after_cursor_execute listener. No-op for SQLite."""
    global _installed
    if _installed:
        return
    if engine.dialect.name != "postgresql":
        _log.info(
            "egress_tracker: skipping install — dialect=%s (only Postgres is tracked)",
            engine.dialect.name,
        )
        return

    @event.listens_for(engine, "after_cursor_execute")
    def _track(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        global _queries_since_flush
        if not statement:
            return
        # Only SELECTs generate egress worth measuring. INSERT/UPDATE/DELETE
        # consume ingress, not egress, and COMMIT/SET are bookkeeping.
        head = statement.lstrip()[:6].upper()
        if head != "SELECT":
            return
        # Skip our own writes if something ever SELECTs the log file row.
        if "egress_log" in statement:
            return
        try:
            rows = cursor.rowcount
        except Exception:
            return
        if rows is None or rows < 0:
            return

        fp = _fingerprint(statement)
        table = _extract_table(statement)
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with _LOCK:
            entry = _COUNTERS.get(fp)
            if entry is None:
                entry = {
                    "calls": 0,
                    "rows": 0,
                    "first_seen": now_iso,
                    "last_seen": now_iso,
                    "table": table,
                    "sample": statement[:400],
                }
                _COUNTERS[fp] = entry
            entry["calls"] += 1
            entry["rows"] += rows
            entry["last_seen"] = now_iso
            _queries_since_flush += 1
            if _queries_since_flush >= _FLUSH_EVERY:
                _flush_locked()
                _queries_since_flush = 0

    _installed = True
    _log.info("egress_tracker: installed (flush every %d queries)", _FLUSH_EVERY)
