"""Submit WhatsApp templates to Meta for approval.

Usage:
    python scripts/submit_wa_templates.py                    # Submit all templates
    python scripts/submit_wa_templates.py b2b_fiber_intro    # Submit one template
    python scripts/submit_wa_templates.py --status           # Check status of all templates
    python scripts/submit_wa_templates.py --list             # List approved templates from Meta

Reads templates from: config/whatsapp/new_templates.yml
Credentials from: .env (WA_WABA_ID, WA_TOKEN)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hf_dashboard"))
from services.wa_template_builder import build_components as _build_components  # noqa: E402

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")

WABA_ID = os.getenv("WA_WABA_ID")
TOKEN = os.getenv("WA_TOKEN")
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

TEMPLATES_FILE = Path(__file__).parent.parent / "config" / "whatsapp" / "new_templates.yml"


def _headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _load_templates() -> dict:
    """Load template definitions from YAML."""
    with open(TEMPLATES_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("templates", {})


def submit_template(name: str, template: dict) -> dict:
    """Submit a single template to Meta for approval."""
    payload = {
        "name": name,
        "language": template.get("language", "en"),
        "category": template.get("category", "MARKETING"),
        "components": _build_components(template),
    }

    url = f"{BASE_URL}/{WABA_ID}/message_templates"
    r = httpx.post(url, headers=_headers(), json=payload, timeout=30)

    result = r.json()
    if r.status_code == 200:
        print(f"  ✅ {name} — Submitted (ID: {result.get('id', '?')}), status: {result.get('status', '?')}")
    else:
        error = result.get("error", {})
        print(f"  ❌ {name} — Failed: {error.get('message', r.text)}")

    return result


def check_status():
    """List all templates and their approval status from Meta."""
    url = f"{BASE_URL}/{WABA_ID}/message_templates"
    params = {"fields": "name,status,category,language,quality_score", "limit": 100}
    r = httpx.get(url, headers=_headers(), params=params, timeout=30)

    if r.status_code != 200:
        print(f"Error: {r.text}")
        return

    templates = r.json().get("data", [])
    print(f"\n{'Name':<35} {'Status':<12} {'Category':<12} {'Language':<8} {'Quality'}")
    print("-" * 80)
    for t in templates:
        status = t.get("status", "?")
        status_icon = {"APPROVED": "🟢", "PENDING": "🟡", "REJECTED": "🔴"}.get(status, "⚪")
        print(f"  {t['name']:<33} {status_icon} {status:<10} {t.get('category', '?'):<12} {t.get('language', '?'):<8} {t.get('quality_score', {}).get('score', '—')}")

    print(f"\nTotal: {len(templates)} templates")


def list_approved():
    """List only approved templates ready to use."""
    url = f"{BASE_URL}/{WABA_ID}/message_templates"
    params = {"fields": "name,status,category,components", "limit": 100}
    r = httpx.get(url, headers=_headers(), params=params, timeout=30)

    templates = r.json().get("data", [])
    approved = [t for t in templates if t.get("status") == "APPROVED"]

    print(f"\nApproved templates ({len(approved)}):\n")
    for t in approved:
        # Count variables
        var_count = 0
        for comp in t.get("components", []):
            text = comp.get("text", "")
            var_count += text.count("{{")

        print(f"  {t['name']:<35} {t.get('category', '?'):<12} {var_count} variables")


def main():
    if not WABA_ID or not TOKEN:
        print("Error: Set WA_WABA_ID and WA_TOKEN in .env")
        sys.exit(1)

    args = sys.argv[1:]

    if "--status" in args:
        check_status()
        return

    if "--list" in args:
        list_approved()
        return

    templates = _load_templates()

    if not templates:
        print("No templates found in", TEMPLATES_FILE)
        return

    # Submit specific template or all
    if args and args[0] not in ("--status", "--list"):
        name = args[0]
        if name not in templates:
            print(f"Template '{name}' not found. Available: {list(templates.keys())}")
            return
        print(f"Submitting template: {name}")
        submit_template(name, templates[name])
    else:
        print(f"Submitting {len(templates)} templates to Meta...\n")
        for name, tpl in templates.items():
            submit_template(name, tpl)

    print("\nDone. Check status with: python scripts/submit_wa_templates.py --status")


if __name__ == "__main__":
    main()
