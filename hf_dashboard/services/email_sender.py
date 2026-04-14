"""Email sender using Gmail API (HTTP-based, works on HF Spaces).

Uses OAuth2 refresh token to send emails via Gmail API over HTTPS.
No SMTP needed — bypasses HF Spaces port blocking.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

from services.config import get_settings


# ─────────────────────────────────────────────────────────────────────────────
# Jinja2 environment — shared by the seed loader (to resolve {% extends %} +
# {% include %}) and the sender's per-recipient string render. Autoescape off
# because we render HTML email bodies, not user-facing web pages.
# ─────────────────────────────────────────────────────────────────────────────

_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "templates" / "emails"

_JINJA_ENV: Environment | None = None


def get_jinja_env() -> Environment:
    """Lazily build the email Jinja2 environment."""
    global _JINJA_ENV
    if _JINJA_ENV is None:
        _JINJA_ENV = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_ROOT)),
            autoescape=select_autoescape(enabled_extensions=(), default=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _JINJA_ENV


def render_template_file(relative_path: str, variables: dict) -> str:
    """Render a template file (with inheritance + includes) to HTML.

    The path is relative to ``hf_dashboard/templates/emails/``. Resolves
    ``{% extends %}`` and ``{% include %}`` against the FileSystemLoader.
    """
    env = get_jinja_env()
    tpl = env.get_template(relative_path)
    return tpl.render(**variables)


def render_template_string(template_content: str, variables: dict) -> str:
    """Render a raw Jinja2 string with variables.

    Used as the backwards-compatible rendering path for any template whose
    HTML lives in the DB instead of on disk (e.g. legacy seeded templates).
    """
    env = get_jinja_env()
    return env.from_string(template_content).render(**variables)


def template_file_exists(slug: str) -> bool:
    """Check whether a seeded template file exists on disk for this slug."""
    return (_TEMPLATES_ROOT / f"{slug}.html").exists()


def render_template_by_slug(slug: str, variables: dict) -> str:
    """Render an email template to HTML for a single recipient.

    Prefers the on-disk file at ``templates/emails/<slug>.html`` — which
    resolves ``{% extends %}`` against the locked shell layout — but falls
    back to rendering the DB row's ``html_content`` if no file exists
    (so future DB-created templates from a UI editor still work).

    The ``variables`` dict should already contain the merged shared
    branding config plus per-recipient send vars (see
    :func:`services.email_personalization.build_send_variables`).
    """
    if template_file_exists(slug):
        return render_template_file(f"{slug}.html", variables)

    # Fallback: render whatever is in the DB row for this slug.
    from services.database import get_db
    from services.models import EmailTemplate

    db = get_db()
    try:
        row = db.query(EmailTemplate).filter(EmailTemplate.slug == slug).first()
        if row is None or not row.html_content:
            raise FileNotFoundError(
                f"No template file on disk and no DB row for slug {slug!r}"
            )
        return render_template_string(row.html_content, variables)
    finally:
        db.close()

log = logging.getLogger(__name__)


class EmailSender:
    """Send emails via Gmail API (HTTPS)."""

    def __init__(self):
        settings = get_settings()
        self.smtp_user = settings.smtp_user
        self.from_name = settings.smtp_from_name
        self.from_email = settings.smtp_from_email
        self.daily_limit = settings.email_daily_limit

        # Gmail API OAuth2 credentials
        self.client_id = os.getenv("GMAIL_CLIENT_ID", "")
        self.client_secret = os.getenv("GMAIL_CLIENT_SECRET", "")
        self.refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "")

        # Also check SMTP password for backward compat display
        self.smtp_password = settings.smtp_password

        self._access_token = None

    def _get_access_token(self) -> str:
        """Get a fresh access token using the refresh token."""
        if not self.refresh_token:
            raise RuntimeError("GMAIL_REFRESH_TOKEN not set")

        response = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        })

        if response.status_code != 200:
            raise RuntimeError(f"Failed to refresh token: {response.text}")

        self._access_token = response.json()["access_token"]
        return self._access_token

    def is_configured(self) -> bool:
        """Check if Gmail API credentials are set."""
        return bool(self.refresh_token and self.client_id and self.client_secret)

    def test_connection(self) -> dict:
        """Test Gmail API connectivity."""
        if not self.is_configured():
            return {"success": False, "message": "Gmail API not configured. Set GMAIL_REFRESH_TOKEN in HF Space secrets."}

        try:
            token = self._get_access_token()
            # Verify by getting user profile
            r = requests.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 200:
                email = r.json().get("emailAddress", "")
                return {"success": True, "message": f"Connected to Gmail API as {email}"}
            return {"success": False, "message": f"Gmail API error: {r.status_code} {r.text}"}
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {e}"}

    def send_email(self, to_email: str, subject: str, html_content: str,
                   plain_text: str = None, reply_to: str = None, to_name: str = None) -> dict:
        """Send a single email via Gmail API."""
        if not self.is_configured():
            return {"success": False, "message": "Gmail API not configured. Set GMAIL_REFRESH_TOKEN in HF Space secrets."}

        try:
            html_content = self._preprocess_html(html_content)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = formataddr((self.from_name, self.from_email))
            msg["To"] = formataddr((to_name, to_email)) if to_name else to_email
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=self.from_email.split("@")[1])
            msg["List-Unsubscribe"] = f"<mailto:{self.from_email}?subject=Unsubscribe>"
            msg["Reply-To"] = reply_to or self.from_email

            if not plain_text:
                plain_text = re.sub("<[^<]+?>", "", html_content)
                plain_text = re.sub(r"\s+", " ", plain_text).strip()[:5000]

            msg.attach(MIMEText(plain_text, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            # Encode message for Gmail API
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

            # Send via Gmail API
            token = self._get_access_token()
            response = requests.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"raw": raw_message},
            )

            if response.status_code == 200:
                msg_id = response.json().get("id", "")
                return {
                    "success": True,
                    "message": f"Sent to {to_email}",
                    "message_id": msg_id,
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                error = response.json().get("error", {}).get("message", response.text)
                return {"success": False, "message": f"Gmail API error: {error}"}

        except Exception as e:
            return {"success": False, "message": f"Failed: {e}"}

    def send_test_email(self, to_email: str) -> dict:
        """Send a test email."""
        html = f"""
        <div style="font-family:Arial; max-width:600px; margin:0 auto; padding:20px;">
            <h2>Test Email from Himalayan Fibres</h2>
            <p>Gmail API is working correctly on HF Spaces.</p>
            <p><strong>Sent at:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p><strong>From:</strong> {self.from_email}</p>
        </div>
        """
        return self.send_email(to_email, "Test Email - Himalayan Fibres Dashboard", html)

    def render_template(self, template_content: str, variables: dict) -> str:
        """Render a template string with Jinja2.

        Backwards-compatible shim around :func:`render_template_string`.
        Pre-existing callers passed a simple HTML blob with ``{{var}}``
        placeholders; Jinja2 handles those identically to the old regex
        path, plus it now supports ``{% if %}`` guards and filters.
        """
        return render_template_string(template_content, variables)

    def _preprocess_html(self, html_content: str) -> str:
        """Make HTML email-client friendly."""
        html_content = re.sub(r"@import\s+url\([^)]+\);?", "", html_content)
        html_content = re.sub(r"<style[^>]*>[\s\S]*?@import[\s\S]*?</style>", "", html_content, flags=re.IGNORECASE)
        if not html_content.strip().lower().startswith("<!doctype") and not html_content.strip().lower().startswith("<html"):
            html_content = f"<!DOCTYPE html><html><head><meta charset='UTF-8'></head><body>{html_content}</body></html>"
        return html_content


def generate_idempotency_key(email_type: str, contact_id: str, reference_id: str = None) -> str:
    """Generate unique key to prevent duplicate sends."""
    parts = [email_type, str(contact_id)]
    if reference_id:
        parts.append(str(reference_id))
    parts.append(datetime.now(timezone.utc).strftime("%Y%m%d"))
    return hashlib.sha256(":".join(parts).encode()).hexdigest()[:32]
