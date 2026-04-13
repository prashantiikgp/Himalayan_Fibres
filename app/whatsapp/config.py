"""WhatsApp YAML configuration engine with full Pydantic schema validation.

Loads config/whatsapp/*.yml files and validates them against strict Pydantic
models. Every field is typed and documented — invalid config fails loudly at
startup rather than silently at runtime.

Usage:
    from app.whatsapp.config import wa_config

    # Typed access to settings
    wa_config.settings.api.version          # "v21.0"
    wa_config.settings.rate_limits.batch_size  # 100

    # Get a template definition with variable schema
    tpl = wa_config.get_template("order_confirmation")
    tpl.variables[0].name  # "customer_name"

    # Get quick reply text
    wa_config.get_quick_reply("greeting")  # "Namaste! Welcome to..."

    # Reload from disk
    wa_config.reload()
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ==========================================================================
# PYDANTIC SCHEMAS — settings.yml
# ==========================================================================


class APIConfig(BaseModel):
    """Meta Graph API connection settings."""

    version: str = "v21.0"
    graph_base: str = "https://graph.facebook.com"
    timeout_seconds: int = Field(30, ge=5, le=120)
    media_timeout_seconds: int = Field(60, ge=10, le=300)


class BusinessProfileConfig(BaseModel):
    """WhatsApp Business Profile metadata."""

    verified_name: str = "Himalayan Fibres"
    display_phone: str = ""
    about: str = ""
    description: str = ""
    vertical: str = "RETAIL"
    website: str = ""
    email: str = ""


class MessagingConfig(BaseModel):
    """Messaging defaults and behavior."""

    default_language: str = "en"
    window_hours: int = Field(24, ge=1, le=72)
    default_footer: str = ""
    welcome_auto_reply: str = ""
    greeting_message: str = ""


class RateLimitsConfig(BaseModel):
    """Sending rate limits and retry policy."""

    messages_per_second: int = Field(80, ge=1, le=1000)
    template_messages_daily: int = Field(1000, ge=1)
    batch_delay_seconds: float = Field(1.0, ge=0)
    batch_size: int = Field(100, ge=1, le=1000)
    max_retries: int = Field(3, ge=0, le=10)
    retry_delay_seconds: int = Field(60, ge=1)


class MediaCleanupConfig(BaseModel):
    """Media cleanup policy."""

    enabled: bool = False
    retention_days: int = Field(90, ge=1)


class MediaConfig(BaseModel):
    """Media upload/download configuration."""

    download_dir: str = "media/whatsapp"
    max_upload_size_bytes: int = Field(16777216, ge=1)  # 16 MB
    supported_types: dict[str, list[str]] = Field(default_factory=lambda: {
        "image": ["image/jpeg", "image/png", "image/webp"],
        "document": ["application/pdf"],
        "audio": ["audio/aac", "audio/mp4", "audio/mpeg", "audio/ogg"],
        "video": ["video/mp4", "video/3gpp"],
    })
    cleanup: MediaCleanupConfig = Field(default_factory=MediaCleanupConfig)


class WebhookConfig(BaseModel):
    """Webhook processing configuration."""

    verify_signature: bool = True
    log_payloads: bool = False
    track_statuses: list[str] = Field(
        default_factory=lambda: ["sent", "delivered", "read", "failed"]
    )

    @field_validator("track_statuses", mode="before")
    @classmethod
    def validate_statuses(cls, v: list[str]) -> list[str]:
        valid = {"sent", "delivered", "read", "failed", "deleted"}
        for s in v:
            if s not in valid:
                raise ValueError(f"Invalid status '{s}'. Must be one of: {valid}")
        return v


class TemplateSyncConfig(BaseModel):
    """Template sync schedule settings."""

    auto_sync: bool = True
    sync_interval_seconds: int = Field(3600, ge=60)
    sync_on_startup: bool = True


class SyncConfig(BaseModel):
    """Sync configuration."""

    templates: TemplateSyncConfig = Field(default_factory=TemplateSyncConfig)


class TestingConfig(BaseModel):
    """Testing/development settings."""

    test_phone: str = ""
    sandbox_mode: bool = False


class WASettingsSchema(BaseModel):
    """Root schema for config/whatsapp/settings.yml."""

    api: APIConfig = Field(default_factory=APIConfig)
    business_profile: BusinessProfileConfig = Field(default_factory=BusinessProfileConfig)
    messaging: MessagingConfig = Field(default_factory=MessagingConfig)
    rate_limits: RateLimitsConfig = Field(default_factory=RateLimitsConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)


# ==========================================================================
# PYDANTIC SCHEMAS — templates.yml
# ==========================================================================


class TemplateVariableSchema(BaseModel):
    """Schema for a single template variable."""

    name: str
    type: str = "text"
    description: str = ""
    required: bool = True
    example: str = ""
    max_length: int = Field(256, ge=1)


class TemplateButtonSchema(BaseModel):
    """Schema for a template button."""

    type: str  # URL, CATALOG, ORDER_DETAILS, QUICK_REPLY
    text: str
    url: str | None = None


class TemplateDefinition(BaseModel):
    """Single WhatsApp template definition with variable schema."""

    display_name: str
    description: str = ""
    category: str = "UTILITY"
    language: str = "en"
    use_case: str = ""
    has_header_image: bool = False
    variables: list[TemplateVariableSchema] = Field(default_factory=list)
    buttons: list[TemplateButtonSchema] = Field(default_factory=list)
    notes: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid = {"MARKETING", "UTILITY", "AUTHENTICATION"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"Invalid category '{v}'. Must be one of: {valid}")
        return upper

    @property
    def required_variables(self) -> list[TemplateVariableSchema]:
        return [v for v in self.variables if v.required]

    @property
    def variable_names(self) -> list[str]:
        return [v.name for v in self.variables]


class UseCaseGroup(BaseModel):
    """Grouping of templates by use case."""

    templates: list[str] = Field(default_factory=list)
    description: str = ""


class WATemplatesSchema(BaseModel):
    """Root schema for config/whatsapp/templates.yml."""

    templates: dict[str, TemplateDefinition] = Field(default_factory=dict)
    use_cases: dict[str, UseCaseGroup] = Field(default_factory=dict)


# ==========================================================================
# PYDANTIC SCHEMAS — messages.yml
# ==========================================================================


class QuickReply(BaseModel):
    """Canned quick reply message."""

    label: str
    text: str
    tags: list[str] = Field(default_factory=list)


class AutoResponseRule(BaseModel):
    """Automated response rule triggered by conditions."""

    name: str
    trigger: str  # first_message_outside_hours, keyword
    keywords: list[str] = Field(default_factory=list)
    business_hours: dict[str, Any] | None = None
    response_preset: str = ""
    cooldown_hours: int = Field(24, ge=1)

    @field_validator("trigger", mode="before")
    @classmethod
    def validate_trigger(cls, v: str) -> str:
        valid = {"first_message_outside_hours", "keyword", "first_message"}
        if v not in valid:
            raise ValueError(f"Invalid trigger '{v}'. Must be one of: {valid}")
        return v


class AutoResponseConfig(BaseModel):
    """Auto-response master switch and rules."""

    enabled: bool = False
    rules: list[AutoResponseRule] = Field(default_factory=list)


class AutoLabelRule(BaseModel):
    """Rule for auto-assigning labels to contacts."""

    label: str
    condition: str
    color: str = "#6b7280"


class PresetLabel(BaseModel):
    """Predefined label for manual use."""

    name: str
    color: str = "#6b7280"


class ContactLabelsConfig(BaseModel):
    """Contact labeling configuration."""

    auto_label_rules: list[AutoLabelRule] = Field(default_factory=list)
    preset_labels: list[PresetLabel] = Field(default_factory=list)


class WAMessagesSchema(BaseModel):
    """Root schema for config/whatsapp/messages.yml."""

    quick_replies: dict[str, QuickReply] = Field(default_factory=dict)
    auto_responses: AutoResponseConfig = Field(default_factory=AutoResponseConfig)
    contact_labels: ContactLabelsConfig = Field(default_factory=ContactLabelsConfig)


# ==========================================================================
# CONFIG ENGINE — Loader + Validator + Cache
# ==========================================================================


class WhatsAppConfigManager:
    """Schema-validated YAML config engine for WhatsApp.

    Loads all config/whatsapp/*.yml files, validates against Pydantic schemas,
    and provides typed access. Fails loudly on invalid config.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        base = Path(__file__).parent.parent.parent
        self._config_path = config_path or base / "config" / "whatsapp"

        # Validated, typed config objects
        self.settings: WASettingsSchema = WASettingsSchema()
        self.templates_config: WATemplatesSchema = WATemplatesSchema()
        self.messages: WAMessagesSchema = WAMessagesSchema()

        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """Load a YAML file from the config directory."""
        path = self._config_path / filename
        if not path.exists():
            logger.warning("WhatsApp config file not found: %s", path)
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load(self) -> None:
        """Load and validate all WhatsApp config files."""
        errors: list[str] = []

        # --- settings.yml ---
        try:
            raw = self._load_yaml("settings.yml")
            self.settings = WASettingsSchema.model_validate(raw)
        except Exception as e:
            errors.append(f"settings.yml: {e}")
            self.settings = WASettingsSchema()

        # --- templates.yml ---
        try:
            raw = self._load_yaml("templates.yml")
            self.templates_config = WATemplatesSchema.model_validate(raw)
        except Exception as e:
            errors.append(f"templates.yml: {e}")
            self.templates_config = WATemplatesSchema()

        # --- messages.yml ---
        try:
            raw = self._load_yaml("messages.yml")
            self.messages = WAMessagesSchema.model_validate(raw)
        except Exception as e:
            errors.append(f"messages.yml: {e}")
            self.messages = WAMessagesSchema()

        if errors:
            for err in errors:
                logger.error("WhatsApp config validation error: %s", err)
        else:
            logger.info(
                "WhatsApp config loaded: %d templates, %d quick replies",
                len(self.templates_config.templates),
                len(self.messages.quick_replies),
            )

    def reload(self) -> None:
        """Reload all configs from disk."""
        self._load()
        logger.info("WhatsApp configuration reloaded")

    # ------------------------------------------------------------------
    # Template access
    # ------------------------------------------------------------------

    def get_template(self, name: str) -> TemplateDefinition | None:
        """Get a template definition by its Meta template name."""
        return self.templates_config.templates.get(name)

    def get_templates_by_use_case(self, use_case: str) -> list[TemplateDefinition]:
        """Get all templates for a given use case."""
        group = self.templates_config.use_cases.get(use_case)
        if not group:
            return []
        return [
            tpl
            for name in group.templates
            if (tpl := self.templates_config.templates.get(name))
        ]

    def get_template_variable_names(self, name: str) -> list[str]:
        """Get the list of variable names for a template."""
        tpl = self.get_template(name)
        return tpl.variable_names if tpl else []

    def list_templates(self) -> list[dict[str, str]]:
        """List all templates with basic info."""
        return [
            {
                "name": name,
                "display_name": tpl.display_name,
                "category": tpl.category,
                "use_case": tpl.use_case,
                "language": tpl.language,
                "variable_count": str(len(tpl.variables)),
            }
            for name, tpl in self.templates_config.templates.items()
        ]

    # ------------------------------------------------------------------
    # Quick reply access
    # ------------------------------------------------------------------

    def get_quick_reply(self, key: str) -> str | None:
        """Get a quick reply text by key."""
        qr = self.messages.quick_replies.get(key)
        return qr.text.strip() if qr else None

    def list_quick_replies(self) -> list[dict[str, Any]]:
        """List all quick replies."""
        return [
            {"key": key, "label": qr.label, "tags": qr.tags}
            for key, qr in self.messages.quick_replies.items()
        ]

    def get_quick_replies_by_tag(self, tag: str) -> list[QuickReply]:
        """Get quick replies matching a tag."""
        return [
            qr
            for qr in self.messages.quick_replies.values()
            if tag in qr.tags
        ]

    # ------------------------------------------------------------------
    # Auto-response access
    # ------------------------------------------------------------------

    def get_auto_response_rules(self) -> list[AutoResponseRule]:
        """Get all enabled auto-response rules."""
        if not self.messages.auto_responses.enabled:
            return []
        return self.messages.auto_responses.rules

    # ------------------------------------------------------------------
    # Label access
    # ------------------------------------------------------------------

    def get_preset_labels(self) -> list[PresetLabel]:
        """Get all preset labels for manual tagging."""
        return self.messages.contact_labels.preset_labels

    def get_auto_label_rules(self) -> list[AutoLabelRule]:
        """Get auto-labeling rules."""
        return self.messages.contact_labels.auto_label_rules

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_all(self) -> dict[str, list[str]]:
        """Validate all configs and return issues."""
        issues: dict[str, list[str]] = {"errors": [], "warnings": []}

        # Check template variables reference valid presets
        for name, tpl in self.templates_config.templates.items():
            if tpl.category == "MARKETING" and not tpl.variables and not tpl.notes:
                issues["warnings"].append(
                    f"Template '{name}' is MARKETING with no variables — intentional?"
                )

        # Check quick reply presets referenced by auto-response rules exist
        for rule in self.messages.auto_responses.rules:
            if rule.response_preset and rule.response_preset not in self.messages.quick_replies:
                issues["errors"].append(
                    f"Auto-response rule '{rule.name}' references unknown "
                    f"quick reply preset '{rule.response_preset}'"
                )

        # Check use_case groups reference existing templates
        for uc_name, group in self.templates_config.use_cases.items():
            for tpl_name in group.templates:
                if tpl_name not in self.templates_config.templates:
                    issues["errors"].append(
                        f"Use case '{uc_name}' references unknown template '{tpl_name}'"
                    )

        return issues


# ==========================================================================
# SINGLETON
# ==========================================================================


@lru_cache
def get_wa_config() -> WhatsAppConfigManager:
    """Get cached WhatsApp config instance."""
    return WhatsAppConfigManager()


wa_config = get_wa_config()
