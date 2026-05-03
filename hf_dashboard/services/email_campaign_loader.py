"""Loader for campaign/email_campaign/ — schema-validated access layer.

Reads + validates every email template sidecar and segment campaign YAML
under ``campaign/email_campaign/`` against ``EmailTemplate`` and
``CampaignFile`` Pydantic schemas. Provides O(1) lookup by name + tier +
segment so dashboard pages don't have to walk the filesystem each render.

Cached at module load (via ``functools.lru_cache``) so repeated calls in
one process are free; restart / ``reload()`` to pick up YAML edits.

Usage:
    from services.email_campaign_loader import (
        load_email_templates,
        load_email_campaigns,
        get_template,
    )

    # All templates
    templates = load_email_templates()           # dict[name, EmailTemplate]

    # Filtered
    blogs = [t for t in templates.values() if t.tier == "blog" and t.status == "READY"]

    # Single lookup
    tpl = get_template("welcome_day_3_sustainability")

    # Campaigns for one segment
    camps = load_email_campaigns()["potential_domestic"]
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

from engines.campaign_schemas import (
    CampaignFile,
    EmailTemplate,
)

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EMAIL_SHARED = _REPO_ROOT / "campaign" / "email_campaign" / "shared"
_EMAIL_HTML_ROOT = _REPO_ROOT / "hf_dashboard" / "templates" / "emails"

_TEMPLATE_DIRS = [
    "company_templates",
    "category_templates",
    "product_templates",
    "lifecycle_templates",
    "transactional_templates",
    "seasonal_templates",
]
_SEGMENT_DIRS = [
    "existing_clients",
    "churned_clients",
    "potential_domestic",
    "international_email",
]


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def load_email_templates() -> dict[str, EmailTemplate]:
    """Load all email template sidecars, return dict keyed by template name.

    Templates with status='RETIRED' are still loaded but consumers should
    filter them out of UI lists. PLANNED templates are loaded so we can
    show 'coming soon' state in the dashboard if useful.

    Raises:
        Pydantic ValidationError if any sidecar fails schema validation.
        Use ``scripts/validate_campaigns.py`` to find errors before
        the dashboard chokes on them.
    """
    out: dict[str, EmailTemplate] = {}
    for sub in _TEMPLATE_DIRS:
        sub_path = _EMAIL_SHARED / sub
        if not sub_path.exists():
            continue
        for path in sorted(sub_path.rglob("*.yml")):
            data = _load_yaml(path)
            tpl = EmailTemplate.model_validate(data)
            if tpl.name in out:
                # Sidecars must have unique names — duplicates indicate
                # an accidental double-write across two folders.
                raise ValueError(
                    f"Duplicate email template name '{tpl.name}': "
                    f"both {out[tpl.name].html_template_file} and {tpl.html_template_file}"
                )
            out[tpl.name] = tpl
    log.info("Loaded %d email templates from %s", len(out), _EMAIL_SHARED)
    return out


@lru_cache(maxsize=1)
def load_email_campaigns() -> dict[str, list]:
    """Load all email segment campaigns, return dict keyed by segment.

    Returns:
        dict[segment_name, list[Campaign]] — only segments with a
        non-empty campaigns.yml are included.
    """
    out: dict[str, list] = {}
    for seg in _SEGMENT_DIRS:
        path = _REPO_ROOT / "campaign" / "email_campaign" / seg / "campaigns.yml"
        if not path.exists():
            continue
        data = _load_yaml(path)
        cfile = CampaignFile.model_validate(data)
        if cfile.campaigns:
            out[seg] = cfile.campaigns
    log.info("Loaded email campaigns for %d segments", len(out))
    return out


def get_template(name: str) -> EmailTemplate | None:
    """Look up a single template by name. Returns None if not found."""
    return load_email_templates().get(name)


def templates_by_tier(tier: str, *, status: str = "READY") -> list[EmailTemplate]:
    """Filter templates by tier (and optionally status)."""
    return [
        t for t in load_email_templates().values()
        if t.tier == tier and (status is None or t.status == status)
    ]


def templates_for_segment(segment: str, *, status: str = "READY") -> list[EmailTemplate]:
    """Templates eligible for a given segment (in their target_segments list)."""
    return [
        t for t in load_email_templates().values()
        if segment in t.target_segments and (status is None or t.status == status)
    ]


def reload() -> None:
    """Clear caches — call this after editing a sidecar YAML at runtime."""
    load_email_templates.cache_clear()
    load_email_campaigns.cache_clear()


def html_template_path(template_name: str) -> Path | None:
    """Return the on-disk Path for a template's HTML body, or None."""
    tpl = get_template(template_name)
    if not tpl:
        return None
    return _EMAIL_HTML_ROOT / tpl.html_template_file
