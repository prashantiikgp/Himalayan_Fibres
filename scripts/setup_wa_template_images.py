"""One-shot pipeline: pull product images from Wix CDN, compress, upload
to Supabase Storage, then patch the campaign/ template YAMLs in place.

Mapping is hardcoded at the top — edit it to swap images.

Usage:
    python scripts/setup_wa_template_images.py
    python scripts/setup_wa_template_images.py --dry-run
    python scripts/setup_wa_template_images.py --bucket wa-template-images

Side effects:
    - Creates Supabase Storage bucket if missing (public-read)
    - Uploads compressed JPEGs (max 1200px width, q85)
    - Edits each template YAML in place: replaces `image: TBD_*` with the
      Supabase public URL
    - Appends entries to campaign/_image_manifest.yml

Requires SUPABASE_URL, SUPABASE_SERVICE_KEY, plus Pillow + httpx.
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
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

DEFAULT_BUCKET = "wa-template-images"
MAX_WIDTH = 1200
JPEG_QUALITY = 85
SHARED = REPO_ROOT / "campaign" / "whatsapp_campaign" / "shared"
MANIFEST_PATH = REPO_ROOT / "campaign" / "_image_manifest.yml"


# template path (relative to SHARED) -> Wix CDN source URL + path prefix
# Pulled from Himalayanfibres Wix store (site 9797eeec...) Stores V1 query.
IMAGE_MAP: list[dict[str, str]] = [
    {
        "yaml": "category_templates/nettle_overview.yml",
        "url": "https://static.wixstatic.com/media/b6e546_905d7394df904c778662d5695b6d352b~mv2.jpg/v1/fit/w_2259,h_1587,q_90/file.jpg",
        "prefix": "category",
        "slug": "nettle-overview",
        "wix_product": "Nettle Yarn",
    },
    {
        "yaml": "category_templates/hemp_overview.yml",
        "url": "https://static.wixstatic.com/media/b6e546_652904bf8569428c9e194e43d5de7455~mv2.png/v1/fit/w_1024,h_1024,q_90/file.png",
        "prefix": "category",
        "slug": "hemp-overview",
        "wix_product": "Himalayan Hemp Yarn",
    },
    {
        "yaml": "category_templates/wool_overview.yml",
        "url": "https://static.wixstatic.com/media/b6e546_5ed56cec2f8844158e161c927e66bbf9~mv2.png/v1/fit/w_1024,h_1024,q_90/file.png",
        "prefix": "category",
        "slug": "wool-overview",
        "wix_product": "Himalayan Wool Yarn",
    },
    {
        "yaml": "category_templates/collections_overview.yml",
        "url": "https://static.wixstatic.com/media/b6e546_5ac02c09b6374122993a8249cf4c6dd4~mv2.png/v1/fit/w_1024,h_1024,q_90/file.png",
        "prefix": "category",
        "slug": "collections-overview",
        "wix_product": "Hand-Dyed Wool Yarn (placeholder for collections)",
    },
    {
        "yaml": "company_templates/company_intro_b2b.yml",
        "url": "https://static.wixstatic.com/media/b6e546_905d7394df904c778662d5695b6d352b~mv2.jpg/v1/fit/w_2259,h_1587,q_90/file.jpg",
        "prefix": "company",
        "slug": "brand-hero",
        "wix_product": "Nettle Yarn (placeholder for brand hero)",
    },
]


def ensure_bucket(bucket: str, dry_run: bool) -> None:
    """Create bucket if missing, public-read."""
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}"}
    get_url = f"{SUPABASE_URL}/storage/v1/bucket/{bucket}"
    r = httpx.get(get_url, headers=headers, timeout=15)
    if r.status_code == 200:
        return
    if r.status_code != 404:
        r.raise_for_status()
    if dry_run:
        print(f"     would create bucket: {bucket}")
        return
    create_url = f"{SUPABASE_URL}/storage/v1/bucket"
    payload = {"id": bucket, "name": bucket, "public": True}
    r = httpx.post(
        create_url, headers={**headers, "Content-Type": "application/json"},
        json=payload, timeout=15,
    )
    r.raise_for_status()
    print(f"     created bucket: {bucket}")


def fetch_and_compress(url: str) -> bytes:
    r = httpx.get(url, follow_redirects=True, timeout=30)
    r.raise_for_status()
    with Image.open(io.BytesIO(r.content)) as im:
        if im.mode in ("RGBA", "P"):
            im = im.convert("RGB")
        if im.width > MAX_WIDTH:
            new_h = int(im.height * MAX_WIDTH / im.width)
            im = im.resize((MAX_WIDTH, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()


def upload(bucket: str, object_path: str, data: bytes) -> str:
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}"
    r = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "image/jpeg",
            "x-upsert": "true",
        },
        content=data,
        timeout=30,
    )
    r.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{object_path}"


def patch_yaml(yaml_path: Path, public_url: str, dry_run: bool) -> bool:
    """Replace `image: TBD_<anything>` line with the Supabase URL.
    Returns True if a change was applied (or would be in dry-run)."""
    text = yaml_path.read_text(encoding="utf-8")
    pattern = re.compile(r"^(\s*image:\s*)TBD_\S+\s*$", re.MULTILINE)
    new_text, n = pattern.subn(rf"\g<1>{public_url}", text)
    if n == 0:
        return False
    if not dry_run:
        yaml_path.write_text(new_text, encoding="utf-8")
    return True


def append_manifest(entries: list[dict]) -> None:
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(f"Bucket: {args.bucket}  (public-read)")
    ensure_bucket(args.bucket, args.dry_run)

    entries: list[dict] = []
    for item in IMAGE_MAP:
        yaml_path = SHARED / item["yaml"]
        if not yaml_path.exists():
            print(f"SKIP {item['yaml']} — file not found")
            continue
        print(f"\n>>>  {item['yaml']}")
        print(f"     wix:  {item['wix_product']}")
        try:
            compressed = fetch_and_compress(item["url"])
        except Exception as e:
            print(f"     FAIL fetch/compress: {e}")
            continue
        h = hashlib.sha1(compressed).hexdigest()[:8]
        object_path = f"{item['prefix']}/{item['slug']}-{h}.jpg"
        size_kb = len(compressed) / 1024
        if args.dry_run:
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{args.bucket}/{object_path}"
            print(f"     would upload {size_kb:.0f} KB -> {public_url}")
        else:
            try:
                public_url = upload(args.bucket, object_path, compressed)
            except httpx.HTTPStatusError as e:
                print(f"     FAIL upload: HTTP {e.response.status_code}: {e.response.text[:200]}")
                continue
            print(f"     uploaded {size_kb:.0f} KB -> {public_url}")
        changed = patch_yaml(yaml_path, public_url, args.dry_run)
        print(f"     yaml patched: {changed}")
        entries.append({
            "template": item["yaml"],
            "wix_source": item["url"],
            "object_path": object_path,
            "public_url": public_url,
            "size_kb": round(size_kb, 1),
        })

    if entries and not args.dry_run:
        append_manifest(entries)
        print(f"\nManifest: {MANIFEST_PATH.relative_to(REPO_ROOT)}")

    print(f"\nDone. {len(entries)} images processed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
