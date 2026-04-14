"""Local media store for WhatsApp template header assets.

Files are written under `${MEDIA_PATH}/wa_headers/` and served by the
dashboard's FastAPI `/media` StaticFiles mount, giving Meta a public HTTPS
URL to pull from at template-submission time.

A ProductMedia row is persisted with `kind='wa_header'` and `public_url`
set, so the row can be referenced later (e.g. re-using an already-uploaded
image across multiple templates).
"""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

from services.config import get_settings
from services.models import ProductMedia

_log = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("_", name).strip("_") or "file"


def _headers_dir() -> Path:
    settings = get_settings()
    root = Path(settings.media_path) / "wa_headers"
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_upload(
    db,
    src_path: str,
    original_filename: str,
    caption: str = "",
) -> ProductMedia:
    """Copy a file into the local media store and persist a ProductMedia row.

    `src_path` is the path Gradio (or any uploader) hands us — typically a
    temp file. We copy it into the wa_headers dir under a unique slug, then
    record the ProductMedia row and return it. The caller can read
    `row.public_url` to get the URL Meta will fetch.
    """
    filename_slug = _slugify(Path(original_filename).name)
    unique = f"{uuid.uuid4().hex[:12]}_{filename_slug}"
    dest = _headers_dir() / unique

    shutil.copyfile(src_path, dest)
    _log.info("wa_headers: stored %s -> %s", original_filename, dest)

    settings = get_settings()
    public_url = f"{settings.public_base_url}/media/wa_headers/{unique}"

    row = ProductMedia(
        filename=unique,
        filepath=str(dest),
        caption=caption,
        kind="wa_header",
        public_url=public_url,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_upload(db, media_id: int) -> bool:
    """Remove a ProductMedia row and its underlying file."""
    row = db.query(ProductMedia).filter(ProductMedia.id == media_id).one_or_none()
    if row is None:
        return False
    try:
        Path(row.filepath).unlink(missing_ok=True)
    except OSError as e:
        _log.warning("wa_headers: could not delete file %s: %s", row.filepath, e)
    db.delete(row)
    db.commit()
    return True


def is_public_url_https() -> bool:
    """Whether the configured PUBLIC_BASE_URL is safe for Meta to pull from."""
    return get_settings().public_base_url.lower().startswith("https://")
