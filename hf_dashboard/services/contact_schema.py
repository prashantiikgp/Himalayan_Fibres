"""Contact schema loader — reads config/contacts/schema.yml.

Provides segments, lifecycle stages, tags, field definitions,
and validation for the Contacts and Inbox pages.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "config" / "contacts" / "schema.yml"


@lru_cache(maxsize=1)
def _load_schema() -> dict:
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("contact_schema", {})


def get_segments() -> list[dict]:
    return _load_schema().get("segments", [])


def get_segment_choices(include_all: bool = True) -> list[str]:
    choices = ["All"] if include_all else []
    for s in get_segments():
        choices.append(s["label"])
    return choices


def get_segment_id_by_label(label: str) -> str | None:
    for s in get_segments():
        if s["label"] == label:
            return s["id"]
    return None


def get_segment_color(segment_id: str) -> str:
    for s in get_segments():
        if s["id"] == segment_id:
            return s.get("color", "#64748b")
    return "#64748b"


def get_segment_description(segment_id: str) -> str:
    for s in get_segments():
        if s["id"] == segment_id:
            return s.get("description", "")
    return ""


def get_lifecycle_stages() -> list[dict]:
    return _load_schema().get("lifecycle_stages", [])


def get_lifecycle_choices(include_all: bool = True) -> list[str]:
    choices = ["All"] if include_all else []
    for s in get_lifecycle_stages():
        choices.append(s["label"])
    return choices


def get_lifecycle_id_by_label(label: str) -> str | None:
    for s in get_lifecycle_stages():
        if s["label"] == label:
            return s["id"]
    return None


def get_lifecycle_color(lifecycle_id: str) -> str:
    for s in get_lifecycle_stages():
        if s["id"] == lifecycle_id:
            return s.get("color", "#64748b")
    return "#64748b"


def get_lifecycle_icon(lifecycle_id: str) -> str:
    for s in get_lifecycle_stages():
        if s["id"] == lifecycle_id:
            return s.get("icon", "")
    return ""


def get_predefined_tags() -> list[str]:
    return _load_schema().get("tags", {}).get("predefined", [])


def get_field_config() -> dict:
    return _load_schema().get("fields", {})


def get_country_options() -> list[str]:
    fields = get_field_config()
    country_field = fields.get("country", {})
    return country_field.get("options", ["India", "US", "UK", "Other"])


def validate_contact(data: dict) -> list[str]:
    """Validate contact data against schema. Returns list of errors."""
    errors = []
    fields = get_field_config()

    for field_name, field_def in fields.items():
        value = data.get(field_name, "").strip()
        if field_def.get("required") and not value:
            errors.append(f"{field_def.get('placeholder', field_name)} is required")
        if value and "validation" in field_def:
            pattern = field_def["validation"]
            if not re.match(pattern, value):
                errors.append(f"{field_name}: invalid format")

    return errors
