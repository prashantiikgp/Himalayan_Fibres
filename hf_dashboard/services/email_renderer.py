"""Email template rendering service using Jinja2.

Ported from app/services/email_renderer.py.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError

from services.config import get_settings

log = logging.getLogger(__name__)


class EmailRenderer:
    """Render email templates with Jinja2 variable substitution."""

    def __init__(self):
        self.env = Environment(loader=BaseLoader(), autoescape=True)
        self.env.filters["currency"] = self._format_currency
        self.env.filters["truncate_words"] = self._truncate_words

    @staticmethod
    def _format_currency(value: float, currency: str = "USD") -> str:
        symbols = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}
        return f"{symbols.get(currency, currency + ' ')}{value:,.2f}"

    @staticmethod
    def _truncate_words(text: str, num_words: int) -> str:
        words = text.split()
        return text if len(words) <= num_words else " ".join(words[:num_words]) + "..."

    def render_string(self, template_str: str, variables: dict[str, Any]) -> str:
        """Render a template string with variables."""
        try:
            template = self.env.from_string(template_str)
            return template.render(**variables)
        except (TemplateSyntaxError, UndefinedError):
            return self._simple_substitute(template_str, variables)

    @staticmethod
    def _simple_substitute(template_str: str, variables: dict[str, Any]) -> str:
        """Regex fallback for {{variable}} substitution."""
        result = template_str
        for key, value in variables.items():
            pattern = r"\{\{\s*" + re.escape(key) + r"\s*\}\}"
            result = re.sub(pattern, str(value) if value else "", result)
        return result

    @staticmethod
    def extract_variables(template_str: str) -> list[str]:
        """Extract {{variable}} names from a template."""
        return list(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", template_str)))

    def validate_template(self, template_str: str, required_vars: list[str] | None = None) -> dict[str, Any]:
        """Validate a template: check syntax, required vars, unsubscribe link."""
        errors, warnings = [], []
        found_vars = self.extract_variables(template_str)

        if required_vars:
            missing = [v for v in required_vars if v not in found_vars]
            if missing:
                errors.append(f"Missing required variables: {', '.join(missing)}")

        if "unsubscribe" not in template_str.lower():
            warnings.append("Template should include an unsubscribe link")

        try:
            self.env.from_string(template_str)
        except TemplateSyntaxError as e:
            errors.append(f"Syntax error: {e}")

        return {"is_valid": len(errors) == 0, "errors": errors, "warnings": warnings, "found_variables": found_vars}

    def render_with_defaults(self, template_str: str, variables: dict[str, Any], defaults: dict[str, Any] | None = None) -> str:
        """Render with default values for missing variables."""
        if defaults is None:
            defaults = self._get_standard_defaults()
        return self.render_string(template_str, {**defaults, **variables})

    @staticmethod
    def _get_standard_defaults() -> dict[str, Any]:
        settings = get_settings()
        return {
            "company_name": "Himalayan Fibers",
            "company_email": settings.smtp_user,
            "company_website": "https://himalayanfibre.com",
            "unsubscribe_url": f"mailto:{settings.smtp_user}?subject=Unsubscribe",
            "current_year": "2026",
            "first_name": "Valued Customer",
            "last_name": "",
        }


email_renderer = EmailRenderer()
