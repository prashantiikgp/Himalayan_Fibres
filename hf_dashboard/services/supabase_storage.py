"""Supabase Storage helper — minimal surface for email-invoice uploads.

Uses ``storage3`` directly (the underlying client shipped inside
``supabase-py``), which is ~10x smaller than the full SDK because we
don't need auth/realtime/postgrest for server-side file uploads.

Requires two env vars in HF Space Secrets:

  SUPABASE_URL           e.g. https://yxlofrkkzjkxtbowyryj.supabase.co
  SUPABASE_SERVICE_KEY   the service_role key (bypasses RLS — server-only)

The service_role key MUST NOT be exposed to the browser or committed to
source. Put it in HF Space → Settings → Variables & Secrets.

Public API
----------

- :func:`ensure_bucket` — create the bucket if it doesn't exist (idempotent).
- :func:`upload_file`  — upload bytes and return a long-lived signed URL.
- :func:`create_signed_url` — regenerate a signed URL for an existing object.
- :func:`delete_file` — remove an object.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

log = logging.getLogger(__name__)

# Default signed-URL expiry — 1 year. Long enough that emails sent today
# still work next year. If an older email's link ever expires, the
# recipient can message us on WhatsApp for a fresh copy.
DEFAULT_EXPIRES_IN = 31_536_000  # 365 days in seconds


class SupabaseStorageError(RuntimeError):
    """Raised when the Supabase storage API returns an error."""


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SupabaseStorageError(
            f"Environment variable {name} is not set. "
            "Add it in HF Space → Settings → Variables & Secrets."
        )
    return value


@lru_cache(maxsize=1)
def _get_client():
    """Lazily build the storage3 client.

    Imported inside the function so the ``storage3`` package only needs
    to be installed when this service is actually used (e.g. not in the
    Phase A smoke test, which doesn't touch Supabase).
    """
    from storage3 import create_client

    url = _require_env("SUPABASE_URL").rstrip("/")
    key = _require_env("SUPABASE_SERVICE_KEY")
    return create_client(
        url=f"{url}/storage/v1",
        headers={
            "apiKey": key,
            "Authorization": f"Bearer {key}",
        },
        is_async=False,
    )


def ensure_bucket(bucket: str, *, public: bool = False) -> None:
    """Create ``bucket`` if it doesn't exist. Idempotent — no-op if present."""
    client = _get_client()
    try:
        existing = {b.id: b for b in client.list_buckets()}
    except Exception as e:
        raise SupabaseStorageError(f"Failed to list buckets: {e}") from e

    if bucket in existing:
        return

    try:
        client.create_bucket(bucket, options={"public": public})
        log.info("Created Supabase bucket: %s (public=%s)", bucket, public)
    except Exception as e:
        raise SupabaseStorageError(f"Failed to create bucket {bucket!r}: {e}") from e


def upload_file(
    bucket: str,
    path: str,
    file_bytes: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload ``file_bytes`` to ``bucket/path`` and return a signed URL.

    Creates the bucket if missing. The returned URL is valid for
    ``DEFAULT_EXPIRES_IN`` seconds (1 year).
    """
    ensure_bucket(bucket, public=False)
    client = _get_client()
    try:
        client.from_(bucket).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )
    except Exception as e:
        raise SupabaseStorageError(
            f"Failed to upload to {bucket}/{path}: {e}"
        ) from e

    return create_signed_url(bucket, path, expires_in=DEFAULT_EXPIRES_IN)


def create_signed_url(
    bucket: str,
    path: str,
    *,
    expires_in: int = DEFAULT_EXPIRES_IN,
) -> str:
    """Return a time-limited signed URL for an object in a private bucket."""
    client = _get_client()
    try:
        res = client.from_(bucket).create_signed_url(path=path, expires_in=expires_in)
    except Exception as e:
        raise SupabaseStorageError(
            f"Failed to sign URL for {bucket}/{path}: {e}"
        ) from e

    # storage3 returns {"signedURL": "..."} on success
    url = res.get("signedURL") or res.get("signed_url") or ""
    if not url:
        raise SupabaseStorageError(
            f"Signed URL missing from response for {bucket}/{path}: {res}"
        )
    return url


def delete_file(bucket: str, path: str) -> None:
    """Remove an object. No-op if the file is already gone."""
    client = _get_client()
    try:
        client.from_(bucket).remove([path])
    except Exception as e:
        raise SupabaseStorageError(
            f"Failed to delete {bucket}/{path}: {e}"
        ) from e
