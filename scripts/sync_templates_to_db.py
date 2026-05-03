"""Sync campaign/ WhatsApp template YAMLs into the wa_templates table.

For each YAML under campaign/whatsapp_campaign/shared/**/*.yml, upserts a
row keyed on (name, language). Sets is_draft=True so the dashboard's
Template Studio can show them before they're submitted to Meta.

Uses Supabase PostgREST with the service-role key (no SQLAlchemy needed).
Requires SUPABASE_URL + SUPABASE_SERVICE_KEY in repo-root .env.

Usage:
    python scripts/sync_templates_to_db.py
    python scripts/sync_templates_to_db.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

sys.path.insert(0, str(REPO_ROOT / "hf_dashboard"))
from services.wa_template_builder import build_components  # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

SHARED = REPO_ROOT / "campaign" / "whatsapp_campaign" / "shared"
SUBDIRS = [
    "company_templates",
    "category_templates",
    "product_templates",
    "utility_templates",
]


def yaml_to_meta_spec(tpl: dict) -> dict:
    """Adapt our campaign/ schema to the dict shape build_components expects.

    Differences:
      campaign/ schema           ->  wa_template_builder spec
      header.format=IMAGE+image  ->  header.type=IMAGE,url=image
      header.format=TEXT+text    ->  header.type=TEXT,text=text
      body + body_example        ->  body.text + body.example
    """
    spec: dict = {}
    h = tpl.get("header") or None
    if h:
        fmt = h.get("format")
        if fmt == "TEXT":
            spec["header"] = {"type": "TEXT", "text": h.get("text", "")}
        elif fmt in ("IMAGE", "VIDEO", "DOCUMENT"):
            spec["header"] = {"type": fmt, "url": h.get("image")}
    spec["body"] = {"text": tpl["body"], "example": tpl.get("body_example", [])}
    if tpl.get("footer"):
        spec["footer"] = {"text": tpl["footer"]}
    if tpl.get("buttons"):
        spec["buttons"] = tpl["buttons"]
    return spec


def yaml_to_db_row(tpl: dict) -> dict:
    """Map campaign/ YAML to wa_templates row fields."""
    spec = yaml_to_meta_spec(tpl)
    components = build_components(spec)

    header_format = None
    header_asset_url = None
    header_text = None
    if tpl.get("header"):
        header_format = tpl["header"].get("format")
        if header_format == "TEXT":
            header_text = tpl["header"].get("text")
        elif header_format in ("IMAGE", "VIDEO", "DOCUMENT"):
            header_asset_url = tpl["header"].get("image")

    return {
        "name": tpl["name"],
        "language": tpl.get("language", "en"),
        "category": tpl["meta_category"],
        "status": "LOCAL_DRAFT",
        "is_draft": True,
        "components": components,
        "body_text": tpl["body"],
        "header_format": header_format,
        "header_asset_url": header_asset_url,
        "header_text": header_text,
        "footer_text": tpl.get("footer"),
        "buttons": tpl.get("buttons", []),
        "variables": tpl.get("body_example", []),
        "rejection_reason": "",
    }


def upsert_rows(rows: list[dict]) -> tuple[int, str]:
    """Delete-then-insert keyed on name. The wa_templates table is
    missing its (name, language) unique constraint in the deployed DB
    (the model declares it but `create_all` never ALTERs existing
    tables), so PostgREST on_conflict won't work. Delete-then-insert
    is idempotent and works without the constraint.
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    names = [r["name"] for r in rows]
    in_clause = ",".join(f'"{n}"' for n in names)
    del_url = (
        f"{SUPABASE_URL}/rest/v1/wa_templates"
        f"?name=in.({in_clause})&is_draft=eq.true"
    )
    dr = httpx.delete(del_url, headers=headers, timeout=30)
    if dr.status_code >= 300:
        return dr.status_code, f"DELETE failed: {dr.text}"
    ins_url = f"{SUPABASE_URL}/rest/v1/wa_templates"
    ir = httpx.post(ins_url, headers=headers, content=json.dumps(rows), timeout=30)
    return ir.status_code, ir.text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows: list[dict] = []
    for sub in SUBDIRS:
        # rglob so nested folders (e.g. product_templates/plant/) are picked up
        for path in sorted((SHARED / sub).rglob("*.yml")):
            with path.open(encoding="utf-8") as f:
                tpl = yaml.safe_load(f)
            row = yaml_to_db_row(tpl)
            rows.append(row)
            print(
                f"  {sub}/{path.name:<40} -> name={row['name']!r:<32} "
                f"meta={row['category']:<10} header={row['header_format']}"
            )

    print(f"\n{len(rows)} rows prepared.")

    if args.dry_run:
        print("DRY RUN — not upserting.")
        return 0

    status, body = upsert_rows(rows)
    if status >= 300:
        print(f"\nERR upsert HTTP {status}: {body[:500]}")
        return 1
    returned = json.loads(body) if body else []
    print(f"\nOK upsert HTTP {status} — {len(returned)} rows synced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
