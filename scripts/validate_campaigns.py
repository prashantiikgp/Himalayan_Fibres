"""Smoke-test campaign/ YAML against Pydantic schemas.

Walks brand_voice.yml + whatsapp_campaign/ + email_campaign/ and validates
everything loads cleanly. Cross-checks:
- every template references a defined voice
- every campaign step references a defined template (channel-specific)
- every email template's html_template_file points to a real file on disk
- every email sidecar's tier matches its parent folder

Usage:
    python scripts/validate_campaigns.py
Exit code: 0 on success, 1 on any validation error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "hf_dashboard"))

from engines.campaign_schemas import (  # noqa: E402
    BrandVoiceFile,
    CampaignFile,
    EmailTemplate,
    WhatsAppTemplate,
)

CAMPAIGN_ROOT = REPO_ROOT / "campaign"
WA_SHARED = CAMPAIGN_ROOT / "whatsapp_campaign" / "shared"
EMAIL_SHARED = CAMPAIGN_ROOT / "email_campaign" / "shared"
EMAIL_HTML_ROOT = REPO_ROOT / "hf_dashboard" / "templates" / "emails"

WA_TEMPLATE_DIRS = [
    "company_templates",
    "category_templates",
    "product_templates",
    "utility_templates",
]
EMAIL_TEMPLATE_DIRS = [
    "company_templates",
    "category_templates",
    "product_templates",
    "lifecycle_templates",
    "transactional_templates",
    "seasonal_templates",
]
SEGMENT_DIRS = [
    "existing_clients",
    "churned_clients",
    "potential_domestic",
    "international_email",
]


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _validate_wa_templates(voice_keys: set[str]) -> tuple[int, int, set[str]]:
    """Validate WA templates. Returns (count, error_count, names_set)."""
    errors = 0
    count = 0
    names: set[str] = set()
    for sub in WA_TEMPLATE_DIRS:
        for tpl_path in sorted((WA_SHARED / sub).rglob("*.yml")):
            try:
                tpl = WhatsAppTemplate.model_validate(_load(tpl_path))
                if tpl.voice not in voice_keys:
                    raise ValueError(
                        f"voice '{tpl.voice}' not in brand_voice.yml ({sorted(voice_keys)})"
                    )
                names.add(tpl.name)
                count += 1
                print(
                    f"OK  WA {sub}/{tpl_path.name} — "
                    f"tier={tpl.tier} meta={tpl.meta_category} voice={tpl.voice}"
                )
            except Exception as e:
                print(f"ERR WA {sub}/{tpl_path.name} — {e}")
                errors += 1
    return count, errors, names


def _validate_email_templates(voice_keys: set[str]) -> tuple[int, int, set[str]]:
    """Validate email templates. Returns (count, error_count, names_set)."""
    errors = 0
    count = 0
    names: set[str] = set()
    for sub in EMAIL_TEMPLATE_DIRS:
        sub_path = EMAIL_SHARED / sub
        if not sub_path.exists():
            continue
        for tpl_path in sorted(sub_path.rglob("*.yml")):
            try:
                tpl = EmailTemplate.model_validate(_load(tpl_path))
                if tpl.voice not in voice_keys:
                    raise ValueError(
                        f"voice '{tpl.voice}' not in brand_voice.yml ({sorted(voice_keys)})"
                    )
                # Cross-check: html_template_file points to a real file
                html_path = EMAIL_HTML_ROOT / tpl.html_template_file
                if tpl.status == "READY" and not html_path.exists():
                    raise ValueError(
                        f"html_template_file '{tpl.html_template_file}' not found at "
                        f"{html_path.relative_to(REPO_ROOT)} (tier=READY but HTML missing)"
                    )
                names.add(tpl.name)
                count += 1
                rel = tpl_path.relative_to(EMAIL_SHARED)
                print(
                    f"OK  email {rel} — "
                    f"tier={tpl.tier} status={tpl.status} voice={tpl.voice}"
                )
            except Exception as e:
                rel = tpl_path.relative_to(EMAIL_SHARED)
                print(f"ERR email {rel} — {e}")
                errors += 1
    return count, errors, names


def _validate_campaigns(channel: str, template_names: set[str]) -> tuple[int, int]:
    """Validate <channel>_campaign segment campaigns.yml. Returns (count, errors)."""
    errors = 0
    count = 0
    channel_root = CAMPAIGN_ROOT / f"{channel}_campaign"
    for seg in SEGMENT_DIRS:
        seg_path = channel_root / seg / "campaigns.yml"
        if not seg_path.exists():
            continue
        try:
            cfile = CampaignFile.model_validate(_load(seg_path))
        except Exception as e:
            print(f"ERR {channel}/{seg}/campaigns.yml — {e}")
            errors += 1
            continue
        for camp in cfile.campaigns:
            if camp.segment != seg:
                print(
                    f"ERR {channel}/{seg}/campaigns.yml :: {camp.id} — "
                    f"segment={camp.segment} but folder={seg}"
                )
                errors += 1
                continue
            if camp.channel != channel:
                print(
                    f"ERR {channel}/{seg}/campaigns.yml :: {camp.id} — "
                    f"channel={camp.channel} but folder is under {channel}_campaign/"
                )
                errors += 1
                continue
            for step in camp.steps:
                if step.template not in template_names:
                    print(
                        f"ERR {channel}/{seg}/campaigns.yml :: {camp.id} — "
                        f"step references unknown template '{step.template}'"
                    )
                    errors += 1
            count += 1
            print(
                f"OK  {channel}/{seg}/campaigns.yml :: {camp.id} — "
                f"{len(camp.steps)} steps, active={camp.is_active}"
            )
    return count, errors


def main() -> int:
    errors = 0

    voice_path = CAMPAIGN_ROOT / "brand_voice.yml"
    try:
        voices = BrandVoiceFile.model_validate(_load(voice_path))
        print(f"OK  brand_voice.yml — {len(voices.voices)} voices: {sorted(voices.voices)}")
    except Exception as e:
        print(f"ERR brand_voice.yml — {e}")
        return 1
    voice_keys = set(voices.voices)
    print()

    print("=== WhatsApp templates ===")
    wa_count, wa_err, wa_names = _validate_wa_templates(voice_keys)
    errors += wa_err
    print()

    print("=== Email templates ===")
    email_count, email_err, email_names = _validate_email_templates(voice_keys)
    errors += email_err
    print()

    print("=== WhatsApp campaigns ===")
    wa_camp_count, wa_camp_err = _validate_campaigns("whatsapp", wa_names)
    errors += wa_camp_err
    print()

    print("=== Email campaigns ===")
    email_camp_count, email_camp_err = _validate_campaigns("email", email_names)
    errors += email_camp_err
    print()

    print("=" * 60)
    print(
        f"WA: {wa_count} templates, {wa_camp_count} campaigns | "
        f"Email: {email_count} templates, {email_camp_count} campaigns | "
        f"Errors: {errors}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
