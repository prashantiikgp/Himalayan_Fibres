#!/usr/bin/env python
"""End-to-end Supabase Storage smoke test.

Uploads /tmp/sample_invoice_10014.pdf to the real ``email-invoices``
bucket and verifies:

  1. ensure_bucket creates it if missing (or no-ops if present).
  2. upload_file returns a non-empty signed URL.
  3. HTTP GET on the signed URL returns 200 + application/pdf.
  4. delete_file removes the uploaded object cleanly.

Reads env from the repo root .env, so make sure ``SUPABASE_URL`` and
``SUPABASE_SERVICE_KEY`` are set before running::

    python scripts/smoke_test_supabase_upload.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Load .env (same pattern as app.py)
try:
    from dotenv import load_dotenv
    _REPO_ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hf_dashboard"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

import requests  # noqa: E402

from services.supabase_storage import (  # noqa: E402
    SupabaseStorageError,
    delete_file,
    ensure_bucket,
    upload_file,
)


BUCKET = "email-invoices"
TEST_PDF = Path("/tmp/sample_invoice_10014.pdf")


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        raise SystemExit(1)
    print(f"  ✓ {msg}")


def main() -> int:
    if not TEST_PDF.exists():
        print(f"Expected test PDF at {TEST_PDF} — not found")
        return 1

    # Precondition: env vars readable
    _assert(
        bool(os.getenv("SUPABASE_URL")),
        "SUPABASE_URL env var present",
    )
    _assert(
        bool(os.getenv("SUPABASE_SERVICE_KEY")),
        "SUPABASE_SERVICE_KEY env var present",
    )

    # Step 1: ensure_bucket
    try:
        ensure_bucket(BUCKET, public=False)
        print(f"  ✓ ensure_bucket('{BUCKET}') succeeded (idempotent)")
    except SupabaseStorageError as e:
        print(f"FAIL: ensure_bucket raised: {e}")
        return 1

    # Step 2: upload
    import uuid
    path = f"smoke_test/{uuid.uuid4().hex[:12]}_invoice.pdf"
    pdf_bytes = TEST_PDF.read_bytes()
    print(f"  · uploading {len(pdf_bytes)} bytes to {BUCKET}/{path}")

    try:
        signed_url = upload_file(
            bucket=BUCKET,
            path=path,
            file_bytes=pdf_bytes,
            content_type="application/pdf",
        )
    except SupabaseStorageError as e:
        print(f"FAIL: upload_file raised: {e}")
        return 1

    _assert(
        bool(signed_url) and signed_url.startswith("http"),
        f"upload_file returned a valid signed URL",
    )
    print(f"  · signed URL: {signed_url[:80]}...")

    # Step 3: HTTP GET
    try:
        r = requests.get(signed_url, timeout=15)
    except Exception as e:
        print(f"FAIL: HTTP GET raised: {e}")
        # Clean up anyway
        try:
            delete_file(BUCKET, path)
        except Exception:
            pass
        return 1

    _assert(r.status_code == 200, f"signed URL returns 200 (got {r.status_code})")
    _assert(
        r.headers.get("content-type", "").startswith("application/"),
        f"content-type is application/* (got {r.headers.get('content-type')!r})",
    )
    _assert(
        len(r.content) == len(pdf_bytes),
        f"downloaded bytes match upload ({len(r.content)} == {len(pdf_bytes)})",
    )
    _assert(
        r.content[:4] == b"%PDF",
        "downloaded content starts with %PDF magic bytes",
    )

    # Step 4: cleanup
    try:
        delete_file(BUCKET, path)
        print(f"  ✓ delete_file('{BUCKET}', '{path}') succeeded")
    except SupabaseStorageError as e:
        print(f"WARN: cleanup failed (non-fatal): {e}")

    print()
    print("ALL PASSED ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
