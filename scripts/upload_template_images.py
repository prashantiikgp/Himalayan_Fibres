"""Compress and upload local images to Supabase Storage for use as
WhatsApp template image headers.

Usage:
    python scripts/upload_template_images.py <local_file>...
    python scripts/upload_template_images.py --bucket wa-template-images <files>
    python scripts/upload_template_images.py --prefix nettle <files>

Behavior:
    For each input image:
    - Resize to max width 1200px (preserves aspect ratio)
    - Compress to JPEG quality 85 (~150-300KB typical)
    - Upload to Supabase Storage at <bucket>/<prefix>/<slug>-<hash>.jpg
    - Print public URL
    - Append entry to campaign/_image_manifest.yml

Why these defaults:
    - Meta WA template image headers: max 5MB, recommended <1MB
    - 1200px wide @ q85 looks crisp on phone screens, ~200KB
    - Public URLs are required because Meta downloads the image
      during template review (Resumable Upload API expects public URL)

Requires:
    - SUPABASE_URL, SUPABASE_SERVICE_KEY in repo-root .env
    - Pillow: pip install Pillow
    - The bucket must exist and be PUBLIC (anon-read).
      One-time setup via Supabase dashboard or:
          curl -X POST "<SUPABASE_URL>/storage/v1/bucket" \\
            -H "Authorization: Bearer <SERVICE_KEY>" \\
            -H "Content-Type: application/json" \\
            -d '{"name":"wa-template-images","public":true}'
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import sys
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

try:
    from PIL import Image
except ImportError:
    print("ERR Pillow not installed. Run: pip install Pillow", file=sys.stderr)
    sys.exit(2)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

DEFAULT_BUCKET = "wa-template-images"
MAX_WIDTH = 1200
JPEG_QUALITY = 85
MANIFEST_PATH = REPO_ROOT / "campaign" / "_image_manifest.yml"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "image"


def compress_image(src: Path) -> bytes:
    with Image.open(src) as im:
        if im.mode in ("RGBA", "P"):
            im = im.convert("RGB")
        if im.width > MAX_WIDTH:
            new_h = int(im.height * MAX_WIDTH / im.width)
            im = im.resize((MAX_WIDTH, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()


def upload_to_supabase(bucket: str, object_path: str, data: bytes) -> str:
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "image/jpeg",
        "x-upsert": "true",
    }
    resp = httpx.post(upload_url, headers=headers, content=data, timeout=30)
    resp.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{object_path}"


def update_manifest(entries: list[dict]) -> None:
    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    images = data.get("images", [])
    images.extend(entries)
    data["images"] = images
    with MANIFEST_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+", help="Local image files to upload")
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--prefix", default="", help="Object path prefix (e.g. 'nettle')")
    args = ap.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERR SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env", file=sys.stderr)
        return 2

    entries: list[dict] = []
    for fp_str in args.files:
        src = Path(fp_str)
        if not src.exists():
            print(f"SKIP {src} — not found")
            continue
        compressed = compress_image(src)
        h = hashlib.sha1(compressed).hexdigest()[:8]
        slug = slugify(src.stem)
        prefix = f"{args.prefix.strip('/').lower()}/" if args.prefix else ""
        object_path = f"{prefix}{slug}-{h}.jpg"
        try:
            url = upload_to_supabase(args.bucket, object_path, compressed)
        except httpx.HTTPStatusError as e:
            print(f"FAIL {src.name} — HTTP {e.response.status_code}: {e.response.text[:200]}")
            continue
        size_kb = len(compressed) / 1024
        print(f"OK   {src.name}  ->  {url}  ({size_kb:.0f} KB)")
        entries.append({
            "source_file": src.name,
            "object_path": object_path,
            "public_url": url,
            "size_kb": round(size_kb, 1),
        })

    if entries:
        update_manifest(entries)
        print(f"\nManifest updated: {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
