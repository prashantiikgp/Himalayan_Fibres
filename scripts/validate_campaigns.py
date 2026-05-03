"""Smoke-test campaign/ YAML against Pydantic schemas.

Walks campaign/brand_voice.yml + campaign/whatsapp_campaign/ and
validates everything loads cleanly. Cross-checks that every
template references a defined voice, and every campaign step
references a defined template.

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
    WhatsAppTemplate,
)

CAMPAIGN_ROOT = REPO_ROOT / "campaign"
WA_SHARED = CAMPAIGN_ROOT / "whatsapp_campaign" / "shared"
TEMPLATE_DIRS = [
    "company_templates",
    "category_templates",
    "product_templates",
    "utility_templates",
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
    template_names: set[str] = set()
    template_count = 0

    for sub in TEMPLATE_DIRS:
        # rglob so templates can live in nested folders, e.g.
        # product_templates/{category,plant,animal,blend}/<name>.yml
        for tpl_path in sorted((WA_SHARED / sub).rglob("*.yml")):
            try:
                tpl = WhatsAppTemplate.model_validate(_load(tpl_path))
                if tpl.voice not in voice_keys:
                    raise ValueError(
                        f"voice '{tpl.voice}' not in brand_voice.yml ({sorted(voice_keys)})"
                    )
                template_names.add(tpl.name)
                template_count += 1
                print(
                    f"OK  {sub}/{tpl_path.name} — "
                    f"tier={tpl.tier} meta={tpl.meta_category} voice={tpl.voice}"
                )
            except Exception as e:
                print(f"ERR {sub}/{tpl_path.name} — {e}")
                errors += 1

    campaign_count = 0
    for seg in SEGMENT_DIRS:
        seg_path = CAMPAIGN_ROOT / "whatsapp_campaign" / seg / "campaigns.yml"
        if not seg_path.exists():
            continue
        try:
            cfile = CampaignFile.model_validate(_load(seg_path))
        except Exception as e:
            print(f"ERR {seg}/campaigns.yml — {e}")
            errors += 1
            continue
        for camp in cfile.campaigns:
            if camp.segment != seg:
                print(
                    f"ERR {seg}/campaigns.yml :: {camp.id} — "
                    f"segment={camp.segment} but folder={seg}"
                )
                errors += 1
                continue
            for step in camp.steps:
                if step.template not in template_names:
                    print(
                        f"ERR {seg}/campaigns.yml :: {camp.id} — "
                        f"step references unknown template '{step.template}'"
                    )
                    errors += 1
            campaign_count += 1
            print(
                f"OK  {seg}/campaigns.yml :: {camp.id} — "
                f"{len(camp.steps)} steps, active={camp.is_active}"
            )

    print()
    print(f"Templates: {template_count}, Campaigns: {campaign_count}, Errors: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
