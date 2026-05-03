"""Submit campaign/ WhatsApp templates to Meta for approval.

Reads YAMLs from campaign/whatsapp_campaign/shared/**/*.yml, builds the
Meta API components payload, posts to the WABA message_templates endpoint,
then flips the wa_templates DB row from `is_draft=true LOCAL_DRAFT` to
`is_draft=false PENDING` with the returned meta_template_id + submitted_at.

Usage:
    # Submit specific templates (recommended for pilot batches)
    python scripts/submit_campaign_wa_templates.py sample_shipped sample_request_thanks followup_interest

    # Dry-run — show what would be posted, don't actually submit
    python scripts/submit_campaign_wa_templates.py --dry-run sample_shipped

    # Submit ALL drafts (use with care — 16 templates at once is risky)
    python scripts/submit_campaign_wa_templates.py --all

Requires .env: WA_TOKEN, WA_WABA_ID, SUPABASE_URL, SUPABASE_SERVICE_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

sys.path.insert(0, str(REPO_ROOT / "hf_dashboard"))
from services.wa_template_builder import build_components  # noqa: E402

WABA_ID = os.environ["WA_WABA_ID"]
WA_TOKEN = os.environ["WA_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

API_VERSION = "v21.0"
META_BASE = f"https://graph.facebook.com/{API_VERSION}"

SHARED = REPO_ROOT / "campaign" / "whatsapp_campaign" / "shared"
SUBDIRS = ["company_templates", "category_templates", "product_templates", "utility_templates"]


def load_template(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_templates(names_filter: set[str] | None = None) -> list[tuple[Path, dict]]:
    out = []
    for sub in SUBDIRS:
        for path in sorted((SHARED / sub).rglob("*.yml")):
            tpl = load_template(path)
            if names_filter is None or tpl["name"] in names_filter:
                out.append((path, tpl))
    return out


def yaml_to_meta_spec(tpl: dict) -> dict:
    """Convert campaign/ schema to the dict shape build_components expects."""
    spec: dict = {}
    h = tpl.get("header") or None
    if h:
        fmt = h.get("format")
        if fmt == "TEXT":
            spec["header"] = {"type": "TEXT", "text": h.get("text", "")}
        elif fmt in ("IMAGE", "VIDEO", "DOCUMENT"):
            spec["header"] = {"type": fmt, "url": h.get("image")}
    body = {"text": tpl["body"]}
    if tpl.get("body_example"):
        body["example"] = tpl["body_example"]
    spec["body"] = body
    if tpl.get("footer"):
        spec["footer"] = {"text": tpl["footer"]}
    if tpl.get("buttons"):
        spec["buttons"] = tpl["buttons"]
    return spec


def submit_to_meta(name: str, language: str, category: str, components: list[dict]) -> tuple[int, dict]:
    url = f"{META_BASE}/{WABA_ID}/message_templates"
    headers = {"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "name": name,
        "language": language,
        "category": category,
        "components": components,
    }
    r = httpx.post(url, headers=headers, json=payload, timeout=30)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:500]}
    return r.status_code, body


def update_db_after_submit(name: str, language: str, meta_id: str, status: str) -> tuple[int, str]:
    """Flip the local row to is_draft=false, set status + meta_template_id."""
    url = f"{SUPABASE_URL}/rest/v1/wa_templates?name=eq.{name}&language=eq.{language}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    body = {
        "is_draft": False,
        "status": status,
        "meta_template_id": meta_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    r = httpx.patch(url, headers=headers, content=json.dumps(body), timeout=30)
    return r.status_code, r.text[:300]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("names", nargs="*", help="Template names to submit (omit if --all)")
    ap.add_argument("--all", action="store_true", help="Submit every draft (use with care)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.all and not args.names:
        print("ERR pass template names, or --all")
        return 2

    filt = None if args.all else set(args.names)
    templates = find_templates(filt)
    if not templates:
        print("ERR no matching templates found")
        return 1

    print(f"Found {len(templates)} template(s) to submit:")
    for path, tpl in templates:
        print(f"  - {tpl['name']} ({tpl['meta_category']}) ← {path.relative_to(REPO_ROOT)}")
    print()

    successes = 0
    failures = 0
    for path, tpl in templates:
        name = tpl["name"]
        language = tpl.get("language", "en")
        category = tpl["meta_category"]
        spec = yaml_to_meta_spec(tpl)
        components = build_components(spec)

        if args.dry_run:
            print(f"DRY {name} — components:")
            print(json.dumps(components, indent=2)[:800])
            print()
            continue

        status_code, resp = submit_to_meta(name, language, category, components)
        if status_code >= 300:
            err = resp.get("error", {}).get("message", str(resp)[:300])
            print(f"FAIL {name} — HTTP {status_code}: {err}")
            failures += 1
            continue

        meta_id = str(resp.get("id", ""))
        meta_status = resp.get("status", "PENDING")
        print(f"OK   {name} — meta_id={meta_id} status={meta_status}")

        db_status, db_body = update_db_after_submit(name, language, meta_id, meta_status)
        if db_status >= 300:
            print(f"     WARN  DB update HTTP {db_status}: {db_body}")
        successes += 1

    print()
    print(f"Submitted: {successes} ok, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
