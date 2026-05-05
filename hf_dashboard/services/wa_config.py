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
    header_text: str = ""
    header_variables: list[TemplateVariable] = Field(default_factory=list)
    variables: list[TemplateVariable] = Field(default_factory=list)
    buttons: list[TemplateButton] = Field(default_factory=list)
    body_text: str = ""
    notes: str = ""

    @property
    def variable_names(self) -> list[str]:
        return [v.name for v in self.variables]

    @property
    def header_variable_names(self) -> list[str]:
        return [v.name for v in self.header_variables]


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
        # templates.yml — flat shape (display_name, body_text, variables[]).
        try:
            raw = self._load_yaml("templates.yml")
            for name, tpl_data in raw.get("templates", {}).items():
                self._templates[name] = TemplateDefinition(**tpl_data)
            for name, uc_data in raw.get("use_cases", {}).items():
                self._use_cases[name] = UseCaseGroup(**uc_data)
        except Exception as e:
            log.error("Failed to load templates.yml: %s", e)

        # new_templates.yml — Meta-component shape (header/body/footer/buttons).
        # Adapt to TemplateDefinition so the broadcast engine can resolve
        # variables for templates created via the new authoring flow.
        # First-load wins: a name in templates.yml is NOT clobbered.
        try:
            raw_new = self._load_yaml("new_templates.yml")
            for name, tpl_data in (raw_new.get("templates") or {}).items():
                if name in self._templates:
                    continue
                adapted = self._adapt_component_template(name, tpl_data)
                if adapted is not None:
                    self._templates[name] = adapted
        except Exception as e:
            log.error("Failed to load new_templates.yml: %s", e)

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

    @staticmethod
    def _extract_placeholders(text: str) -> list[str]:
        """Pull {{1}}, {{name}} placeholders out of `text` in first-seen order."""
        import re

        seen: list[str] = []
        for m in re.finditer(r"\{\{\s*([\w]+)\s*\}\}", text or ""):
            name = m.group(1)
            if name not in seen:
                seen.append(name)
        return seen

    @classmethod
    def _adapt_component_template(
        cls, name: str, tpl_data: dict
    ) -> TemplateDefinition | None:
        """Convert a component-shaped row from new_templates.yml into a
        flat TemplateDefinition. Header + body placeholders are merged
        in declaration order so the broadcast engine resolves them with
        the same numeric/named lookup it uses for templates.yml rows."""
        try:
            header = tpl_data.get("header") or {}
            body = tpl_data.get("body") or {}
            footer = tpl_data.get("footer") or {}
            header_text = (header.get("text") or "") if isinstance(header, dict) else ""
            body_text = (body.get("text") or "") if isinstance(body, dict) else ""
            footer_text = (footer.get("text") or "") if isinstance(footer, dict) else ""

            header_placeholders = cls._extract_placeholders(header_text)
            body_placeholders = cls._extract_placeholders(body_text)
            header_variables = [
                TemplateVariable(name=p, type="text", required=True)
                for p in header_placeholders
            ]
            variables = [
                TemplateVariable(name=p, type="text", required=True)
                for p in body_placeholders
            ]

            buttons_raw = tpl_data.get("buttons") or []
            buttons: list[TemplateButton] = []
            for b in buttons_raw:
                if not isinstance(b, dict):
                    continue
                buttons.append(
                    TemplateButton(
                        type=str(b.get("type") or "QUICK_REPLY"),
                        text=str(b.get("text") or ""),
                        url=b.get("url"),
                    )
                )

            return TemplateDefinition(
                display_name=tpl_data.get("display_name") or name.replace("_", " ").title(),
                description=tpl_data.get("description") or "",
                category=str(tpl_data.get("category") or "UTILITY").upper(),
                language=str(tpl_data.get("language") or "en"),
                use_case=str(tpl_data.get("use_case") or ""),
                has_header_image=(
                    isinstance(header, dict)
                    and str(header.get("type") or "").upper() == "IMAGE"
                ),
                header_image_url=(
                    str(header.get("example", "") or "")
                    if isinstance(header, dict)
                    and str(header.get("type") or "").upper() == "IMAGE"
                    else ""
                ),
                header_text=header_text,
                header_variables=header_variables,
                variables=variables,
                buttons=buttons,
                body_text=body_text,
                notes=footer_text,
            )
        except Exception as e:
            log.error("Failed to adapt new_templates.yml row %r: %s", name, e)
            return None

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
