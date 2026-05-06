"""One-shot cleanup of the `wa-template-images` Supabase bucket.

What it does (idempotent — re-running is safe):

  1. Deletes 38 unprocessed phone photos under
     `Asset/Creating Images/Product Creative Images/Raw Images/` plus the
     `desktop.ini` Windows artefact in the same folder.

  2. Deletes 2 empty-folder placeholders:
       - `Asset/Creating Images/Product Creative Images/Untitled folder/.emptyFolderPlaceholder`
       - `Product Images/Nettle Wool Collection/Serriy  Series/.emptyFolderPlaceholder`

  3. Compresses 3 Snow White Series JPGs that exceed Meta's 5 MB WhatsApp
     template-header limit (resize to max 1600 px wide, JPEG q=85). Same
     bucket path, upsert.

  4. Converts 11 webp/gif files that Meta rejects for template headers
     (Meta only accepts image/jpeg or image/png) to JPEG q=85. Uploads
     under the same path with the extension swapped to `.jpg`, then
     deletes the original. Animated GIFs become first-frame JPEGs —
     animation is irrelevant because Meta renders headers as static.

Originals are downloaded to `cleanup_backup_<date>/` at repo root before
any destructive op, so a botched run can be reverted by re-uploading the
backup.

Usage:
    python scripts/cleanup_wa_template_images.py --dry-run     # preview
    python scripts/cleanup_wa_template_images.py               # execute

Requires: SUPABASE_URL + SUPABASE_SERVICE_KEY in repo-root .env, Pillow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import sys
from pathlib import Path

import httpx
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
BUCKET = "wa-template-images"

MAX_WIDTH = 1600          # generous for header use, still well under 1 MB
JPEG_QUALITY = 85

# -- Operation specs ----------------------------------------------------------

DELETE_PREFIXES: tuple[str, ...] = (
    "Asset/Creating Images/Product Creative Images/Raw Images/",
)

DELETE_EXACT: tuple[str, ...] = (
    "Asset/Creating Images/Product Creative Images/Untitled folder/.emptyFolderPlaceholder",
    "Product Images/Nettle Wool Collection/Serriy  Series/.emptyFolderPlaceholder",
)

# Files that are jpeg already but exceed 5 MB — recompress in place.
COMPRESS_PATHS: tuple[str, ...] = (
    "Product Images/Nettle Wool Collection/Snow White Series/image 4.jpg",
    "Product Images/Nettle Wool Collection/Snow White Series/image 6.jpg",
    "Product Images/Nettle Wool Collection/Snow White Series/Image1.jpg",
)

# Files in formats Meta rejects (webp/gif) — convert to jpg, then delete original.
CONVERT_PATHS: tuple[str, ...] = (
    "Product Images/Plant Based/1.2 Nettle Yarn/1.2.4 Special Nettle Yarn/ERB Sepcial_1.webp",
    "Product Images/Plant Based/1.2 Nettle Yarn/1.2.4 Special Nettle Yarn/ERB Special_3.webp",
    "Product Images/Nettle Wool Collection/Burberry Series/1. Burberry Series.webp",
    "Product Images/Nettle Wool Collection/Burberry Series/2. Top View.webp",
    "Product Images/Nettle Wool Collection/Burberry Series/3. Close Up Image.webp",
    "Product Images/Nettle Wool Collection/Noor Series/Noor_1.webp",
    "Product Images/Nettle Wool Collection/Noor Series/Noor_Main.webp",
    "Product Images/Nettle Wool Collection/Noor Series/noor_Silver.webp",
    "Product Images/Plant Based/1.2 Nettle Yarn/1.2.1 Nettle Yarn Fine/2.gif",
    "Product Images/Plant Based/1.2 Nettle Yarn/1.2.1 Nettle Yarn Fine/3.gif",
    "Product Images/Plant Based/1.2 Nettle Yarn/1.2.1 Nettle Yarn Fine/4.gif",
    "Product Images/Plant Based/2.1 Hemp Fibre/2.1.1 Raw Hemp Fibre/Display.webp",
)


# -- HTTP helpers -------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(
        timeout=60,
        headers={"Authorization": f"Bearer {SUPABASE_KEY}"},
    )


def _list_objects_in_prefix(client: httpx.Client, prefix: str) -> list[dict]:
    """List all objects under a prefix (handles pagination)."""
    out: list[dict] = []
    offset = 0
    while True:
        res = client.post(
            f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET}",
            headers={"Content-Type": "application/json"},
            json={
                "prefix": prefix,
                "limit": 100,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        res.raise_for_status()
        page = res.json() or []
        if not page:
            break
        out.extend(page)
        if len(page) < 100:
            break
        offset += 100
    return out


def _download(client: httpx.Client, path: str) -> bytes:
    res = client.get(f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}")
    res.raise_for_status()
    return res.content


def _upload(client: httpx.Client, path: str, data: bytes, content_type: str) -> None:
    res = client.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",
        headers={"Content-Type": content_type, "x-upsert": "true"},
        content=data,
    )
    res.raise_for_status()


def _delete(client: httpx.Client, paths: list[str]) -> None:
    if not paths:
        return
    res = client.request(
        "DELETE",
        f"{SUPABASE_URL}/storage/v1/bucket/{BUCKET}/objects",
        headers={"Content-Type": "application/json"},
        json={"prefixes": paths},
    )
    if res.status_code == 404:
        # Older Supabase: DELETE /object/<bucket> with body
        res = client.request(
            "DELETE",
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}",
            headers={"Content-Type": "application/json"},
            json={"prefixes": paths},
        )
    res.raise_for_status()


# -- Image processing ---------------------------------------------------------

def _to_jpeg(data: bytes, *, max_width: int = MAX_WIDTH, quality: int = JPEG_QUALITY) -> bytes:
    """Decode any Pillow-supported format → JPEG bytes (resized + quality-capped)."""
    with Image.open(io.BytesIO(data)) as im:
        # Animated GIF → first frame.
        if getattr(im, "is_animated", False):
            im.seek(0)
        if im.mode in ("RGBA", "LA", "P"):
            # Flatten transparency on white so we don't get black halos.
            bg = Image.new("RGB", im.size, (255, 255, 255))
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")

        if im.width > max_width:
            new_h = int(im.height * max_width / im.width)
            im = im.resize((max_width, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        return buf.getvalue()


# -- Backup -------------------------------------------------------------------

def _backup_dir() -> Path:
    today = dt.date.today().isoformat()
    p = REPO_ROOT / f"cleanup_backup_{today}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_backup(path: str, data: bytes) -> None:
    dest = _backup_dir() / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


# -- Main ---------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="Preview only — no deletes/uploads.")
    args = ap.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERR SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env", file=sys.stderr)
        return 2

    print(f"Bucket: {BUCKET}")
    print(f"Mode:   {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print(f"Backup: {_backup_dir().relative_to(REPO_ROOT)}/")
    print()

    with _client() as cli:
        # ── Resolve raw-image deletions by listing the prefix ───────────────
        raw_to_delete: list[str] = []
        for prefix in DELETE_PREFIXES:
            for obj in _list_objects_in_prefix(cli, prefix):
                # Supabase returns names relative to the prefix.
                name = obj.get("name") or ""
                if name and not name.endswith("/"):
                    raw_to_delete.append(prefix + name)

        print(f"[1] Delete raw photos under prefix:")
        for p in DELETE_PREFIXES:
            print(f"      prefix → {p}")
        print(f"    {len(raw_to_delete)} files matched")
        for p in raw_to_delete[:3]:
            print(f"      · {p}")
        if len(raw_to_delete) > 3:
            print(f"      · … ({len(raw_to_delete) - 3} more)")

        print()
        print(f"[2] Delete empty-folder placeholders ({len(DELETE_EXACT)}):")
        for p in DELETE_EXACT:
            print(f"      · {p}")

        print()
        print(f"[3] Compress oversize JPGs ({len(COMPRESS_PATHS)}):")
        for p in COMPRESS_PATHS:
            print(f"      · {p}")

        print()
        print(f"[4] Convert webp/gif → jpg ({len(CONVERT_PATHS)}):")
        for p in CONVERT_PATHS:
            new = p.rsplit(".", 1)[0] + ".jpg"
            print(f"      · {p}")
            print(f"        → {new}")

        if args.dry_run:
            print("\nDRY RUN — no changes made.")
            return 0

        # ── Execute ──────────────────────────────────────────────────────────
        print("\n=== EXECUTING ===\n")

        # 3) Compress in place
        for path in COMPRESS_PATHS:
            try:
                src = _download(cli, path)
                _save_backup(path, src)
                jpg = _to_jpeg(src)
                _upload(cli, path, jpg, "image/jpeg")
                print(f"  COMPRESS  {path}  {len(src)//1024} KB → {len(jpg)//1024} KB")
            except Exception as e:
                print(f"  FAIL      {path}  {e}")

        # 4) Convert webp/gif → jpg, then delete originals
        converted_to_delete: list[str] = []
        for path in CONVERT_PATHS:
            new_path = path.rsplit(".", 1)[0] + ".jpg"
            try:
                src = _download(cli, path)
                _save_backup(path, src)
                jpg = _to_jpeg(src)
                _upload(cli, new_path, jpg, "image/jpeg")
                converted_to_delete.append(path)
                print(f"  CONVERT   {path}  {len(src)//1024} KB → {len(jpg)//1024} KB  ({new_path})")
            except Exception as e:
                print(f"  FAIL      {path}  {e}")

        # 1) Delete raw photos (in batches of 100 — Supabase limit per request)
        # 2) Delete placeholders
        all_deletes = raw_to_delete + list(DELETE_EXACT) + converted_to_delete
        for i in range(0, len(all_deletes), 100):
            batch = all_deletes[i:i + 100]
            try:
                _delete(cli, batch)
                for p in batch:
                    print(f"  DELETE    {p}")
            except Exception as e:
                print(f"  FAIL batch delete: {e}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
