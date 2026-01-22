"""Email template rendering service using Jinja2."""

import re
from typing import Any

from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailRenderer:
    """Service for rendering email templates with variable substitution."""

    def __init__(self):
        self.env = Environment(
            loader=BaseLoader(),
            autoescape=True,
        )

        # Register custom filters
        self.env.filters["currency"] = self._format_currency
        self.env.filters["truncate_words"] = self._truncate_words

    def _format_currency(self, value: float, currency: str = "USD") -> str:
        """Format a number as currency."""
        symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "INR": "₹",
        }
        symbol = symbols.get(currency, currency + " ")
        return f"{symbol}{value:,.2f}"

    def _truncate_words(self, text: str, num_words: int) -> str:
        """Truncate text to a number of words."""
        words = text.split()
        if len(words) <= num_words:
            return text
        return " ".join(words[:num_words]) + "..."

    def render_string(
        self,
        template_str: str,
        variables: dict[str, Any],
    ) -> str:
        """
        Render a template string with variables.

        Args:
            template_str: Template string with {{variable}} placeholders
            variables: Dict of variable names to values

        Returns:
            Rendered string
        """
        # Convert {{var}} to Jinja2 {{ var }} syntax if needed
        # (CloudHQ templates might use different syntax)
        normalized = self._normalize_template(template_str)

        try:
            template = self.env.from_string(normalized)
            return template.render(**variables)
        except TemplateSyntaxError as e:
            logger.error("Template syntax error", error=str(e))
            # Return original with simple substitution as fallback
            return self._simple_substitute(template_str, variables)
        except UndefinedError as e:
            logger.warning("Undefined variable in template", error=str(e))
            return self._simple_substitute(template_str, variables)

    def _normalize_template(self, template_str: str) -> str:
        """
        Normalize template syntax.

        Handles both {{variable}} and {{ variable }} syntax.
        """
        # Already valid Jinja2 syntax
        return template_str

    def _simple_substitute(
        self,
        template_str: str,
        variables: dict[str, Any],
    ) -> str:
        """
        Simple string substitution fallback.

        Replaces {{variable}} with the variable value.
        """
        result = template_str

        for key, value in variables.items():
            # Handle {{variable}} pattern
            pattern = r"\{\{\s*" + re.escape(key) + r"\s*\}\}"
            result = re.sub(pattern, str(value) if value else "", result)

        return result

    def extract_variables(self, template_str: str) -> list[str]:
        """
        Extract variable names from a template.

        Returns list of variable names found in {{variable}} patterns.
        """
        # Find all {{variable}} patterns
        pattern = r"\{\{\s*(\w+)\s*\}\}"
        matches = re.findall(pattern, template_str)
        return list(set(matches))

    def validate_template(
        self,
        template_str: str,
        required_vars: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Validate a template.

        Args:
            template_str: Template string to validate
            required_vars: List of required variable names

        Returns:
            dict with is_valid, errors, warnings, found_vars
        """
        errors = []
        warnings = []

        # Extract variables from template
        found_vars = self.extract_variables(template_str)

        # Check for required variables
        if required_vars:
            missing = [v for v in required_vars if v not in found_vars]
            if missing:
                errors.append(f"Missing required variables: {', '.join(missing)}")

        # Check for unsubscribe link (required for campaign emails)
        if "unsubscribe" not in template_str.lower():
            warnings.append("Template should include an unsubscribe link for campaigns")

        # Try to parse as Jinja2
        try:
            self.env.from_string(self._normalize_template(template_str))
        except TemplateSyntaxError as e:
            errors.append(f"Template syntax error: {str(e)}")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "found_variables": found_vars,
        }

    def render_with_defaults(
        self,
        template_str: str,
        variables: dict[str, Any],
        defaults: dict[str, Any] | None = None,
    ) -> str:
        """
        Render template with default values for missing variables.

        Args:
            template_str: Template string
            variables: Variable values
            defaults: Default values for missing variables

        Returns:
            Rendered string
        """
        if defaults is None:
            defaults = self._get_standard_defaults()

        # Merge defaults with provided variables (provided takes precedence)
        merged = {**defaults, **variables}

        return self.render_string(template_str, merged)

    def _get_standard_defaults(self) -> dict[str, Any]:
        """Get standard default values for common template variables."""
        return {
            "company_name": "Himalayan Fibers",
            "company_email": settings.smtp_user,
            "company_website": "https://himalayanfibre.com",
            "unsubscribe_url": "{{unsubscribe_url}}",  # Placeholder
            "current_year": "2026",
            "first_name": "Valued Customer",
            "last_name": "",
        }


# Singleton instance
email_renderer = EmailRenderer()
