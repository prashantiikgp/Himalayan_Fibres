"""Plan D Phase 0 post-processor.

Fetches the egress tracker snapshot from the running HF Space (or a
saved JSON file), joins each query fingerprint with the per-table
row-width estimates from `hf_dashboard/config/cache/egress_row_widths.yml`,
and prints a top-N ranked report by estimated bytes pulled.

Usage:
    # Fetch live from HF Space (requires the Space to be running)
    python scripts/egress_report.py

    # Specify a different Space URL
    python scripts/egress_report.py --url https://your-space.hf.space

    # Read from a saved JSON file instead of fetching
    python scripts/egress_report.py --file egress_snapshot.json

    # Show more rows
    python scripts/egress_report.py --top 20

    # Dump raw JSON for archival before a fix, then diff after
    python scripts/egress_report.py --fetch-only > baseline.json
    # ... ship fixes ...
    python scripts/egress_report.py --fetch-only > after.json
    # (diff-compare manually)

The report groups queries by fingerprint, pulls the table name from the
FROM clause via regex, multiplies (rows × bytes/row), sorts descending,
and prints a table plus a per-table summary.

The row-width YAML is schema-validated via `engines.cache_schemas`,
matching the engine-config-rule — typos or stale keys fail loudly at
load time. Missing tables fall back to a default width and are flagged
with `?` so you know to add them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hf_dashboard"))

_DEFAULT_SPACE_URL = "https://prashantiitkgp08-himalayan-fibers-dashboard.hf.space"
_DEFAULT_BYTES_PER_ROW = 200

_FROM_RE = re.compile(r"FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


def _fetch_snapshot(url: str) -> dict[str, Any]:
    """GET /_egress/snapshot and return the counters dict."""
    import httpx

    endpoint = url.rstrip("/") + "/_egress/snapshot"
    r = httpx.get(endpoint, timeout=30)
    r.raise_for_status()
    payload = r.json()
    if "counters" not in payload:
        raise SystemExit(f"Unexpected payload shape at {endpoint}: {list(payload)[:5]}")
    return payload["counters"]


def _load_from_file(path: str) -> dict[str, Any]:
    """Read a saved snapshot JSON file."""
    data = json.loads(Path(path).read_text())
    if "counters" in data:
        return data["counters"]
    return data  # assume it's already the counters dict


def _extract_table(fingerprint: str) -> str:
    """Return the first table name referenced in the FROM clause, or '?'."""
    m = _FROM_RE.search(fingerprint or "")
    return m.group(1).lower() if m else "?"


def _row_widths() -> tuple[dict[str, int], int]:
    """Load per-table row widths from YAML via the dashboard config loader."""
    from loader.config_loader import get_config_loader

    cfg = get_config_loader().load_egress_row_widths()
    # Pydantic allows extras so we dump to a flat dict and drop non-int entries
    widths = {}
    for k, v in cfg.row_widths.model_dump().items():
        if isinstance(v, int) and v > 0:
            widths[k] = v
    return widths, _DEFAULT_BYTES_PER_ROW


def _format_bytes(n: int) -> str:
    """Human-readable byte formatting (KiB, MiB)."""
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MiB"
    if n >= 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n} B"


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _render_report(counters: dict[str, Any], top_n: int = 10) -> None:
    widths, default_width = _row_widths()
    rows = []
    unknown_tables: set[str] = set()

    for fingerprint, entry in counters.items():
        rows_returned = int(entry.get("rows", 0))
        calls = int(entry.get("calls", 0))
        sample = entry.get("sample", "")
        first_seen = entry.get("first_seen", "")
        last_seen = entry.get("last_seen", "")

        # Prefer the tracker's stored table field (runs against the
        # full statement at track time) over re-extracting from the
        # truncated sample. Older snapshots without the field fall
        # back to sample-regex extraction.
        table = entry.get("table") or _extract_table(sample)
        width = widths.get(table)
        if width is None:
            unknown_tables.add(table)
            width = default_width
            table_label = f"{table} ?"
        else:
            table_label = table
        est_bytes = rows_returned * width
        rows.append({
            "table": table_label,
            "calls": calls,
            "rows": rows_returned,
            "est_bytes": est_bytes,
            "sample": sample,
            "first_seen": first_seen,
            "last_seen": last_seen,
        })

    rows.sort(key=lambda r: r["est_bytes"], reverse=True)

    # ── Top offenders table ────────────────────────────────────────
    print()
    print("═" * 100)
    print(f"TOP {top_n} EGRESS OFFENDERS (ranked by estimated bytes pulled)")
    print("═" * 100)
    header = f"{'rank':>4}  {'table':<24}  {'calls':>6}  {'rows':>10}  {'est.bytes':>12}  sample"
    print(header)
    print("-" * 100)
    for i, r in enumerate(rows[:top_n], start=1):
        sample_short = _truncate(r["sample"].replace("\n", " "), 40)
        print(
            f"{i:>4}  {r['table']:<24}  {r['calls']:>6}  {r['rows']:>10}  "
            f"{_format_bytes(r['est_bytes']):>12}  {sample_short}"
        )

    # ── Per-table totals ───────────────────────────────────────────
    table_totals: dict[str, dict[str, int]] = {}
    for r in rows:
        t = r["table"].replace(" ?", "")
        agg = table_totals.setdefault(t, {"calls": 0, "rows": 0, "est_bytes": 0})
        agg["calls"] += r["calls"]
        agg["rows"] += r["rows"]
        agg["est_bytes"] += r["est_bytes"]

    table_ranked = sorted(
        table_totals.items(), key=lambda kv: kv[1]["est_bytes"], reverse=True
    )

    print()
    print("═" * 100)
    print("PER-TABLE TOTALS")
    print("═" * 100)
    print(f"{'table':<24}  {'calls':>8}  {'rows':>12}  {'est.bytes':>14}")
    print("-" * 100)
    grand_bytes = 0
    grand_rows = 0
    grand_calls = 0
    for table, agg in table_ranked:
        print(
            f"{table:<24}  {agg['calls']:>8}  {agg['rows']:>12}  "
            f"{_format_bytes(agg['est_bytes']):>14}"
        )
        grand_bytes += agg["est_bytes"]
        grand_rows += agg["rows"]
        grand_calls += agg["calls"]
    print("-" * 100)
    print(
        f"{'TOTAL':<24}  {grand_calls:>8}  {grand_rows:>12}  "
        f"{_format_bytes(grand_bytes):>14}"
    )

    # ── Flagged unknowns ───────────────────────────────────────────
    if unknown_tables:
        print()
        print("⚠ Unknown tables (using default bytes/row, update ")
        print("  hf_dashboard/config/cache/egress_row_widths.yml to fix):")
        for t in sorted(unknown_tables):
            print(f"   - {t or '(no match)'}")

    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan D Phase 0 — egress tracker report",
    )
    parser.add_argument(
        "--url", default=os.environ.get("SPACE_URL", _DEFAULT_SPACE_URL),
        help="HF Space base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--file", default=None,
        help="Read snapshot JSON from file instead of fetching",
    )
    parser.add_argument(
        "--top", type=int, default=10, help="Top-N offenders to show (default: 10)",
    )
    parser.add_argument(
        "--fetch-only", action="store_true",
        help="Print raw snapshot JSON to stdout, skip the report",
    )
    args = parser.parse_args()

    if args.file:
        counters = _load_from_file(args.file)
    else:
        counters = _fetch_snapshot(args.url)

    if args.fetch_only:
        print(json.dumps({"counters": counters}, indent=2, sort_keys=True))
        return 0

    if not counters:
        print("Tracker snapshot is empty — either the Space just rebooted or")
        print("no Postgres queries have fired yet. Give it a minute and retry.")
        return 0

    _render_report(counters, top_n=args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
