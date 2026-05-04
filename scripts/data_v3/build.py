"""CLI orchestrator: build Data/Data_v3/*.csv from Data/Data_v2/*.xlsx.

Pipeline:
    1. extract  — read each source spreadsheet into ContactV3 records
    2. within-file dedup — collapse rows that share email/phone/company
    3. drop unreachable — no email and no phone => can't contact, drop
    4. cross-file dedup — enforce category priority (existing > lapsed
       > carpet > yarn) so the same identity never appears twice
    5. validate — invariants must hold (no email/phone collision across
       categories, every surviving row is reachable)
    6. write   — Data/Data_v3/0X_*.csv plus _build_report.md

Run from repo root:
    python -m scripts.data_v3.build
    python -m scripts.data_v3.build --dry-run
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .dedup import DedupStats, dedup_across, dedup_within, drop_unreachable
from .extract import (
    extract_carpet_exporters,
    extract_existing_clients,
    extract_lapsed_clients,
    extract_yarn_stores,
)
from .schema import Category, ContactV3
from .validate import validate

SOURCE_DIR = Path("Data/Data_v2")
OUTPUT_DIR = Path("Data/Data_v3")

OUTPUT_FILES = {
    Category.EXISTING_CLIENT:     OUTPUT_DIR / "01_existing_clients.csv",
    Category.LAPSED_CLIENT:       OUTPUT_DIR / "02_lapsed_clients.csv",
    Category.CARPET_EXPORTER_LEAD: OUTPUT_DIR / "03_carpet_exporters_india.csv",
    Category.YARN_STORE_LEAD:     OUTPUT_DIR / "04_yarn_stores_international.csv",
}

CSV_FIELDS = ["email", "phone", "first_name", "last_name", "company", "country", "category", "source_file"]


def run_pipeline() -> tuple[dict[Category, list[ContactV3]], DedupStats, dict[Category, int]]:
    raw: dict[Category, list[ContactV3]] = {
        Category.EXISTING_CLIENT:      extract_existing_clients(SOURCE_DIR / "Existing Client.xlsx"),
        Category.LAPSED_CLIENT:        extract_lapsed_clients(SOURCE_DIR / "Churned client.xlsx"),
        Category.CARPET_EXPORTER_LEAD: extract_carpet_exporters(SOURCE_DIR / "Indian_Carpet_Exporter.xlsx"),
        Category.YARN_STORE_LEAD:      extract_yarn_stores(SOURCE_DIR / "International Yarn Store.xlsx"),
    }
    raw_counts = {cat: len(rows) for cat, rows in raw.items()}
    stats = DedupStats()

    cleaned: dict[Category, list[ContactV3]] = {}
    for cat, rows in raw.items():
        rows = dedup_within(rows, stats)
        rows = drop_unreachable(rows, stats)
        cleaned[cat] = rows

    final = dedup_across(cleaned, stats)
    return final, stats, raw_counts


def write_csvs(buckets: dict[Category, list[ContactV3]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for cat, rows in buckets.items():
        path = OUTPUT_FILES[cat]
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            w.writeheader()
            for r in rows:
                d = r.model_dump()
                d["category"] = r.category.value
                w.writerow({k: (d[k] if d[k] is not None else "") for k in CSV_FIELDS})


def write_report(
    buckets: dict[Category, list[ContactV3]],
    stats: DedupStats,
    raw_counts: dict[Category, int],
) -> None:
    val = validate(buckets)
    lines: list[str] = []
    lines.append("# Data v3 build report\n")
    lines.append("## Row counts: source → cleaned\n")
    lines.append("| Category | Raw rows | Within-file collapsed | Unreachable dropped | Cross-file dropped | Final |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cat in Category:
        cross = sum(v for (a, _), v in stats.cross_file_dropped.items() if a == cat)
        lines.append(
            f"| {cat.value} | {raw_counts[cat]} | "
            f"{stats.within_file_collapsed.get(cat, 0)} | "
            f"{stats.unreachable_dropped.get(cat, 0)} | "
            f"{cross} | "
            f"{val.counts_per_category[cat]} |"
        )

    lines.append("\n## Reachability of surviving rows\n")
    lines.append("| Category | Final | With email | With phone |")
    lines.append("|---|---:|---:|---:|")
    for cat in Category:
        lines.append(
            f"| {cat.value} | {val.counts_per_category[cat]} | "
            f"{val.emails_per_category[cat]} | {val.phones_per_category[cat]} |"
        )

    lines.append("\n## Cross-file collisions (lower-priority bucket lost the row)\n")
    if not stats.cross_file_dropped:
        lines.append("_None — buckets were already disjoint after within-file dedup._")
    else:
        lines.append("| Dropped from | Already in | Count |")
        lines.append("|---|---|---:|")
        for (loser, winner), n in sorted(stats.cross_file_dropped.items()):
            lines.append(f"| {loser.value} | {winner.value} | {n} |")

    lines.append("\n## Country distribution per category\n")
    for cat in Category:
        if not val.countries_per_category.get(cat):
            continue
        lines.append(f"\n**{cat.value}**\n")
        lines.append("| Country | Count |")
        lines.append("|---|---:|")
        for country, n in sorted(val.countries_per_category[cat].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {country} | {n} |")

    lines.append("\n## Validation\n")
    if val.ok:
        lines.append("All invariants hold. No email/phone appears in more than one category.")
    else:
        lines.append("ERRORS:")
        for e in val.errors:
            lines.append(f"- {e}")

    (OUTPUT_DIR / "_build_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Run pipeline but don't write any files")
    args = p.parse_args()

    final, stats, raw_counts = run_pipeline()

    print("\nRaw -> Final:")
    for cat in Category:
        print(f"  {cat.value:25s}  {raw_counts[cat]:5d}  ->  {len(final[cat]):5d}")

    val = validate(final)
    print("\nValidation:", "OK" if val.ok else f"FAILED ({len(val.errors)} errors)")
    for e in val.errors[:10]:
        print(f"  - {e}")

    if args.dry_run:
        print("\n(dry-run — no files written)")
        return 0 if val.ok else 1

    write_csvs(final)
    write_report(final, stats, raw_counts)
    print(f"\nWrote {len(final)} CSVs + _build_report.md to {OUTPUT_DIR}/")
    return 0 if val.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
