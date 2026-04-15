"""Seed the ``email_templates`` table from the filesystem.

Each template is a pair:

  hf_dashboard/templates/emails/<slug>.html              ← Jinja2 template
  hf_dashboard/config/email/templates_seed/<slug>.meta.yml ← metadata

The seed loader writes only metadata (slug, name, subject_template,
category, required_variables, is_active) into ``email_templates``. The
HTML body is NOT pre-compiled — at send time we render the on-disk file
in a single pass with both shared branding vars and per-recipient vars
in scope. This keeps ``{% if invoice_url %}`` guards working and avoids
multi-pass Jinja2 undefined-variable gymnastics.

Seed policy
-----------
Default is "seed once, never overwrite" — if a row with this slug
already exists we skip it, so founder edits via a future template
editor are preserved. Pass ``force=True`` to overwrite metadata
(``is_active`` is still preserved even under force).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from services.email_sender import template_file_exists
from services.models import EmailTemplate

log = logging.getLogger(__name__)

_CFG_DIR = Path(__file__).resolve().parent.parent / "config" / "email" / "templates_seed"


class TemplateVariableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str = ""
    type: str = "text"      # text | textarea | url | date
    placeholder: str = ""
    example: str = ""
    required: bool = False


class SeedTemplateMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    category: str = "campaign"
    subject_template: str = ""
    is_active: bool = True
    required_variables: list[str] = Field(default_factory=list)
    optional_variables: list[str] = Field(default_factory=list)
    variables: list[TemplateVariableSpec] = Field(default_factory=list)


class _SeedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: SeedTemplateMeta


def _load_meta(path: Path) -> SeedTemplateMeta:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _SeedDocument(**raw).template


@lru_cache(maxsize=32)
def get_template_meta(slug: str) -> SeedTemplateMeta | None:
    """Load a template's meta YAML for runtime UI use. Cached per-process.

    Used by the Email Broadcast page to render per-variable input widgets.
    Returns None if the slug has no meta file (UI then falls back to
    showing no variable inputs — e.g. welcome, order_delivered_feedback).
    """
    path = _CFG_DIR / f"{slug}.meta.yml"
    if not path.exists():
        return None
    try:
        return _load_meta(path)
    except Exception:
        log.exception("Failed to load template meta: %s", path)
        return None


def seed_email_templates(db: Session, *, force: bool = False) -> dict:
    """Seed all templates under config/email/templates_seed/.

    Returns ``{"inserted": N, "skipped": M, "updated": K}``.

    For each meta YAML:

    - Verify a matching ``<slug>.html`` file exists on disk (otherwise
      skip with a warning — the seeded row would be unrenderable).
    - If no row with this slug exists → insert (counts as inserted).
    - If a row exists and ``force=True`` → update metadata, preserve
      ``is_active`` (counts as updated).
    - If a row exists and ``force=False`` → skip (counts as skipped).

    ``html_content`` is left empty on new rows because the sender renders
    directly from the file via :func:`email_sender.render_template_by_slug`.
    """
    if not _CFG_DIR.exists():
        log.info("Email template seed directory not found: %s — skipping", _CFG_DIR)
        return {"inserted": 0, "skipped": 0, "updated": 0}

    inserted = skipped = updated = 0
    for meta_path in sorted(_CFG_DIR.glob("*.meta.yml")):
        try:
            meta = _load_meta(meta_path)
        except Exception:
            log.exception("Invalid seed meta YAML: %s", meta_path)
            continue

        if not template_file_exists(meta.slug):
            log.warning(
                "Seed meta %s references missing template file %s.html — skipping",
                meta_path.name,
                meta.slug,
            )
            continue

        existing = (
            db.query(EmailTemplate)
            .filter(EmailTemplate.slug == meta.slug)
            .first()
        )

        if existing is None:
            tpl = EmailTemplate(
                slug=meta.slug,
                name=meta.name,
                category=meta.category,
                email_type=meta.category,
                subject_template=meta.subject_template,
                html_content="",  # rendered from file at send time
                required_variables=meta.required_variables,
                is_active=meta.is_active,
            )
            db.add(tpl)
            inserted += 1
            log.info("Seeded email template: %s", meta.slug)
        elif force:
            existing.name = meta.name
            existing.category = meta.category
            existing.email_type = meta.category
            existing.subject_template = meta.subject_template
            existing.required_variables = meta.required_variables
            # is_active intentionally preserved
            # html_content intentionally left unchanged — sender reads from file
            updated += 1
            log.info("Reseeded email template metadata: %s", meta.slug)
        else:
            skipped += 1

    db.commit()
    return {"inserted": inserted, "skipped": skipped, "updated": updated}
