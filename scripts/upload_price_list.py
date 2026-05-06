"""Upload (or refresh) the canonical price-list PDF to Supabase Storage.

Run this whenever the price list changes:

    python scripts/upload_price_list.py "/mnt/g/My Drive/1. Media & Marketing/9. Customer Engagement/Catalogue _Distribution/XYZ_Price_List_16_Aug.pdf"

What it does:
    1. Reads the PDF from disk (default: founder's Drive-synced path).
    2. Uploads to ``email-invoices/canonical/current_price_list.pdf``
       in Supabase Storage, overwriting whatever was there before.
    3. Generates a fresh 1-year signed URL.
    4. Patches ``hf_dashboard/config/email/shared.yml::shared.price_list_pdf_url``
       in place with the new URL.
    5. Reminds you to commit + redeploy so the HF Space picks up the new YAML.

Why mirror to Supabase instead of pointing at the Drive file directly:
    - Drive direct-download URLs require the file to be publicly shared,
      and the URL format is fragile.
    - Supabase signed URLs work without any sharing configuration on
      Drive's side and are stable for a year.
    - Mirroring also lets us audit downloads via Supabase's storage logs.

Auth: needs SUPABASE_URL and SUPABASE_SERVICE_KEY in the environment
(both already present in the repo-root .env).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = (
    "/mnt/g/My Drive/1. Media & Marketing/9. Customer Engagement/"
    "Catalogue _Distribution/XYZ_Price_List_16_Aug.pdf"
)
SHARED_YML = REPO_ROOT / "hf_dashboard" / "config" / "email" / "shared.yml"


def _load_env() -> None:
    """Load repo-root .env into os.environ if not already set."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    import os
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _patch_shared_yml(new_url: str) -> bool:
    """Replace the price_list_pdf_url line in shared.yml. Returns True if changed."""
    text = SHARED_YML.read_text(encoding="utf-8")
    pattern = re.compile(r'^(\s*price_list_pdf_url:\s*)"[^"]*"', re.MULTILINE)
    new_text, n = pattern.subn(rf'\1"{new_url}"', text)
    if n == 0:
        raise RuntimeError(
            "Could not find price_list_pdf_url in shared.yml to patch."
        )
    if new_text == text:
        return False
    SHARED_YML.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Refresh the canonical price-list PDF.")
    p.add_argument(
        "source",
        nargs="?",
        default=DEFAULT_PATH,
        help=f"Path to the PDF (default: {DEFAULT_PATH})",
    )
    p.add_argument(
        "--no-patch",
        action="store_true",
        help="Upload only — don't patch shared.yml (useful for dry-runs).",
    )
    args = p.parse_args()

    src = Path(args.source)
    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 1

    _load_env()
    sys.path.insert(0, str(REPO_ROOT / "hf_dashboard"))
    from services.supabase_storage import upload_file  # noqa: E402

    data = src.read_bytes()
    print(f"Read {len(data):,} bytes from {src.name}")

    url = upload_file(
        "email-invoices",
        "canonical/current_price_list.pdf",
        data,
        content_type="application/pdf",
    )
    print(f"Uploaded → {url[:100]}...")

    if args.no_patch:
        print("--no-patch set; skipping shared.yml update.")
        print("Manually paste the URL above into shared.yml::shared.price_list_pdf_url.")
        return 0

    if _patch_shared_yml(url):
        print(f"Patched {SHARED_YML.relative_to(REPO_ROOT)} with new signed URL.")
        print("\nNext steps:")
        print("  1. git diff hf_dashboard/config/email/shared.yml   # review")
        print("  2. git commit -am 'refresh price-list PDF'")
        print("  3. python scripts/deploy_hf_v2.py                  # ship")
    else:
        print("shared.yml already had this URL; no change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
