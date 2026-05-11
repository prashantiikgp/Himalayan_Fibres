"""One-shot: download social-icon PNGs and upload to the public Supabase
bucket so email footers don't depend on icons8 (Gmail image-proxy flakiness).

Run once:
    python scripts/upload_social_icons.py

Prints the 3 public URLs to paste into
``hf_dashboard/config/email/shared.yml``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
BUCKET = "wa-template-images"
PREFIX = "Asset/Social Icons"

SOURCES = {
    "whatsapp.png": "https://img.icons8.com/color/96/whatsapp--v1.png",
    "instagram.png": "https://img.icons8.com/color/96/instagram-new--v1.png",
    "facebook.png": "https://img.icons8.com/color/96/facebook-new.png",
}


def upload(path: str, data: bytes) -> str:
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "image/png",
        "x-upsert": "true",
    }
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}"
    r = httpx.put(url, headers=headers, content=data, timeout=30)
    if r.status_code >= 400:
        print(f"ERR upload failed for {path}: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{path.replace(' ', '%20')}"


def main() -> None:
    for filename, src in SOURCES.items():
        print(f"-> {filename}")
        r = httpx.get(src, timeout=30, follow_redirects=True)
        if r.status_code != 200:
            print(f"ERR download {src}: {r.status_code}", file=sys.stderr)
            sys.exit(1)
        public_url = upload(f"{PREFIX}/{filename}", r.content)
        print(f"   {public_url}")


if __name__ == "__main__":
    main()
