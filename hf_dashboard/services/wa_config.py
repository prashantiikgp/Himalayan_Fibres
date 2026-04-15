"""WhatsApp YAML config loader.

Ported from app/whatsapp/config.py — loads config/whatsapp/*.yml
and provides typed access to templates, quick replies, auto-responses.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "whatsapp"


# -- Pydantic schemas --

class TemplateVariable(BaseModel):
    name: str
    type: str = "text"
    description: str = ""
    required: bool = True
    example: str = ""
    max_length: int = 256


class TemplateButton(BaseModel):
    type: str
    text: str
    url: str | None = None


class TemplateDefinition(BaseModel):
    display_name: str
    description: str = ""
    category: str = "UTILITY"
    language: str = "en"
    use_case: str = ""
    has_header_image: bool = False
    header_image_url: str = ""
    variables: list[TemplateVariable] = Field(default_factory=list)
    buttons: list[TemplateButton] = Field(default_factory=list)
    body_text: str = ""
    notes: str = ""

    @property
    def variable_names(self) -> list[str]:
        return [v.name for v in self.variables]


class UseCaseGroup(BaseModel):
    templates: list[str] = Field(default_factory=list)
    description: str = ""


class QuickReply(BaseModel):
    label: str
    text: str
    tags: list[str] = Field(default_factory=list)


class AutoResponseRule(BaseModel):
    name: str
    trigger: str
    keywords: list[str] = Field(default_factory=list)
    business_hours: dict[str, Any] | None = None
    response_preset: str = ""
    cooldown_hours: int = 24


class AutoResponseConfig(BaseModel):
    enabled: bool = False
    rules: list[AutoResponseRule] = Field(default_factory=list)


class ContactLabelsConfig(BaseModel):
    auto_label_rules: list[dict] = Field(default_factory=list)
    preset_labels: list[dict] = Field(default_factory=list)


# -- Config manager --

class WAConfigManager:
    """Loads and validates WhatsApp YAML configs."""

    def __init__(self, config_path: Path = _CONFIG_DIR):
        self._path = config_path
        self._templates: dict[str, TemplateDefinition] = {}
        self._use_cases: dict[str, UseCaseGroup] = {}
        self._quick_replies: dict[str, QuickReply] = {}
        self._auto_responses: AutoResponseConfig = AutoResponseConfig()
        self._contact_labels: ContactLabelsConfig = ContactLabelsConfig()
        self._load()

    def _load_yaml(self, filename: str) -> dict:
        path = self._path / filename
        if not path.exists():
            log.warning("WA config not found: %s", path)
            return {}
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load(self):
        # templates.yml
        try:
            raw = self._load_yaml("templates.yml")
            for name, tpl_data in raw.get("templates", {}).items():
                self._templates[name] = TemplateDefinition(**tpl_data)
            for name, uc_data in raw.get("use_cases", {}).items():
                self._use_cases[name] = UseCaseGroup(**uc_data)
        except Exception as e:
            log.error("Failed to load templates.yml: %s", e)

        # messages.yml
        try:
            raw = self._load_yaml("messages.yml")
            for key, qr_data in raw.get("quick_replies", {}).items():
                self._quick_replies[key] = QuickReply(**qr_data)
            ar = raw.get("auto_responses", {})
            if ar:
                self._auto_responses = AutoResponseConfig(**ar)
            cl = raw.get("contact_labels", {})
            if cl:
                self._contact_labels = ContactLabelsConfig(**cl)
        except Exception as e:
            log.error("Failed to load messages.yml: %s", e)

        log.info("WA config: %d templates, %d quick replies", len(self._templates), len(self._quick_replies))

    def reload(self):
        self._templates.clear()
        self._quick_replies.clear()
        self._load()

    # -- Template access --

    def get_template(self, name: str) -> TemplateDefinition | None:
        return self._templates.get(name)

    def list_templates(self) -> list[dict[str, str]]:
        return [
            {"name": name, "display_name": t.display_name, "category": t.category,
             "use_case": t.use_case, "language": t.language,
             "variable_count": str(len(t.variables)),
             "has_body_text": "true" if t.body_text else "false"}
            for name, t in self._templates.items()
        ]

    def get_template_names(self) -> list[str]:
        return list(self._templates.keys())

    def get_template_categories(self) -> list[str]:
        return sorted({t.category for t in self._templates.values() if t.category})

    def get_templates_by_category(self, category: str) -> list[str]:
        if not category or category == "All":
            return self.get_template_names()
        return [name for name, t in self._templates.items() if t.category == category]

    def get_template_variable_names(self, name: str) -> list[str]:
        tpl = self.get_template(name)
        return tpl.variable_names if tpl else []

    # -- Quick reply access --

    def get_quick_reply(self, key: str) -> str | None:
        qr = self._quick_replies.get(key)
        return qr.text.strip() if qr else None

    def list_quick_replies(self) -> list[dict[str, Any]]:
        return [{"key": k, "label": qr.label, "text": qr.text, "tags": qr.tags}
                for k, qr in self._quick_replies.items()]

    # -- Auto-response --

    def get_auto_response_rules(self) -> list[AutoResponseRule]:
        if not self._auto_responses.enabled:
            return []
        return self._auto_responses.rules


@lru_cache(maxsize=1)
def get_wa_config() -> WAConfigManager:
    return WAConfigManager()
