"""Email sender supporting two transports.

1. **Gmail API** (default — HTTP-based, works on HF Spaces).
   Uses OAuth2 refresh token to send via the Gmail API over HTTPS.
   The catch: Gmail rewrites the MIME From header to whatever account
   the OAuth refresh token belongs to. So if your refresh token is for
   account X, every email comes from X — `SMTP_FROM_EMAIL` is ignored.

2. **SMTP** (alternative — smtplib over STARTTLS).
   Honors `SMTP_FROM_EMAIL` literally. Pick this when you need to send
   from a domain alias (e.g. `info@himalayanfibres.com`) without
   re-authorizing the Gmail OAuth.
   Note: HF Spaces *had* outbound port issues with SMTP in the past;
   587 has been observed working as of Phase 7.8.

Transport selection (env var `EMAIL_TRANSPORT`):
  - `gmail_api` → use Gmail API (requires GMAIL_REFRESH_TOKEN).
  - `smtp`      → use SMTP (requires SMTP_PASSWORD).
  - `auto` (default) → Gmail API if GMAIL_REFRESH_TOKEN is set,
    else SMTP if SMTP_PASSWORD is set, else fail loud.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, Undefined, select_autoescape

from services.config import get_settings


class SafeUndefined(Undefined):
    """Render-safe Undefined: a missing variable degrades to an empty
    string instead of 500-ing the whole send.

    B12 — many templates do ``'…' + some_var + '…'`` string concat.
    With Jinja's default ``Undefined`` that raises ``UndefinedError`` when
    the var is missing, killing the entire email. For transactional/
    marketing email a blank is always better than a failed send; the
    per-template copy review (Wave 4) + regression (Wave 5) catch blanks.
    Booleans still work (``{% if var %}`` → falsy), so conditional blocks
    are unaffected.
    """

    __slots__ = ()

    def __str__(self) -> str:  # {{ var }}
        return ""

    def __html__(self) -> str:
        return ""

    def __add__(self, other):  # 'x' ... NO; var + 'y'
        return other if isinstance(other, str) else ""

    def __radd__(self, other):  # 'x' + var
        return other if isinstance(other, str) else ""

    def __iter__(self):
        return iter(())

    def __bool__(self) -> bool:
        return False

    def __getattr__(self, _name):
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Jinja2 environment — shared by the seed loader (to resolve {% extends %} +
# {% include %}) and the sender's per-recipient string render. Autoescape off
# because we render HTML email bodies, not user-facing web pages.
# ─────────────────────────────────────────────────────────────────────────────

_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "templates" / "emails"
_TEMPLATES_DIR = _TEMPLATES_ROOT.parent  # .../templates

# Standalone (non-shell) templates that live OUTSIDE templates/emails/ — full
# self-contained HTML, not the {% extends 'layout/base.html' %} shell. Paths
# are relative to templates/. Single source of truth: database.py seeds the
# same files into DB rows, but the renderer now prefers these files so edits
# propagate via the normal deploy flow (previously the renderer used a stale
# DB copy seeded once, so edits to these files silently never took effect).
NON_SHELL_TEMPLATE_FILES: dict[str, str] = {
    "b2b_introduction": "campaigns/b2b_introduction_carpet_exporters.html",
    "sustainability": "campaigns/sustainability_compliance_campaign.html",
    "tariff_advantage": "campaigns/tariff_advantage_campaign.html",
    # Wave 6 dedup: the 3 near-identical campaign-welcome slugs now render
    # ONE canonical shell template (subjects still differ per slug/flow).
    "welcome_final": "emails/welcome_campaign.html",
    "welcome_production": "emails/welcome_campaign.html",
    "welcome_transactional": "emails/welcome_campaign.html",
}

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
            undefined=SafeUndefined,  # B12: missing var → '' not a 500
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
    """Check whether an on-disk template file exists for this slug —
    either the shell template ``emails/<slug>.html`` or a registered
    standalone template under ``templates/`` (campaigns/, transactional/)."""
    if (_TEMPLATES_ROOT / f"{slug}.html").exists():
        return True
    rel = NON_SHELL_TEMPLATE_FILES.get(slug)
    return bool(rel and (_TEMPLATES_DIR / rel).exists())


def render_template_by_slug(slug: str, variables: dict) -> str:
    """Render an email template to HTML for a single recipient.

    Resolution order:
      1. ``templates/emails/<slug>.html`` — shell template (resolves
         ``{% extends %}`` against the locked layout).
      2. A registered standalone file in ``NON_SHELL_TEMPLATE_FILES``
         (campaigns/, transactional/) — rendered as a self-contained
         string. Preferred over the DB so edits to these files ship via
         the normal deploy flow.
      3. The DB row's ``html_content`` (UI-created / legacy templates).

    The ``variables`` dict should already contain the merged shared
    branding config plus per-recipient send vars (see
    :func:`services.email_personalization.build_send_variables`).
    """
    if (_TEMPLATES_ROOT / f"{slug}.html").exists():
        return render_template_file(f"{slug}.html", variables)

    rel = NON_SHELL_TEMPLATE_FILES.get(slug)
    if rel and (_TEMPLATES_DIR / rel).exists():
        text = (_TEMPLATES_DIR / rel).read_text(encoding="utf-8")
        return render_template_string(text, variables)

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
    """Send emails via Gmail API (HTTPS) or SMTP (smtplib + STARTTLS).

    Pick the transport via the `EMAIL_TRANSPORT` env var (`gmail_api` |
    `smtp` | `auto`). `auto` is the default — uses Gmail API if a
    refresh token is set, falls back to SMTP otherwise.
    """

    TRANSPORT_GMAIL = "gmail_api"
    TRANSPORT_SMTP = "smtp"

    def __init__(self):
        settings = get_settings()
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_password = settings.smtp_password
        self.from_name = settings.smtp_from_name
        self.from_email = settings.smtp_from_email
        self.daily_limit = settings.email_daily_limit

        # Gmail API OAuth2 credentials
        self.client_id = os.getenv("GMAIL_CLIENT_ID", "")
        self.client_secret = os.getenv("GMAIL_CLIENT_SECRET", "")
        self.refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "")

        self._access_token = None
        self.transport = self._choose_transport()

    def _choose_transport(self) -> str:
        """Resolve `EMAIL_TRANSPORT` env var, with sensible auto-detect."""
        explicit = os.getenv("EMAIL_TRANSPORT", "auto").strip().lower()
        if explicit == self.TRANSPORT_GMAIL:
            return self.TRANSPORT_GMAIL
        if explicit == self.TRANSPORT_SMTP:
            return self.TRANSPORT_SMTP
        # auto: prefer Gmail API if creds set, else SMTP if SMTP_PASSWORD
        # set, else default to gmail_api (will fail loud at send time
        # with a clear message).
        if self.refresh_token and self.client_id and self.client_secret:
            return self.TRANSPORT_GMAIL
        if self.smtp_password and self.smtp_user:
            return self.TRANSPORT_SMTP
        return self.TRANSPORT_GMAIL

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
        """True iff the active transport has the credentials it needs."""
        if self.transport == self.TRANSPORT_SMTP:
            return bool(self.smtp_user and self.smtp_password and self.smtp_host)
        return bool(self.refresh_token and self.client_id and self.client_secret)

    def test_connection(self) -> dict:
        """Probe the active transport. Returns {success, message}."""
        if self.transport == self.TRANSPORT_SMTP:
            return self._test_smtp_connection()
        return self._test_gmail_connection()

    def _test_gmail_connection(self) -> dict:
        if not (self.refresh_token and self.client_id and self.client_secret):
            return {
                "success": False,
                "message": "Gmail API not configured. Set GMAIL_REFRESH_TOKEN in HF Space secrets.",
            }

        try:
            token = self._get_access_token()
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

    def _test_smtp_connection(self) -> dict:
        if not (self.smtp_user and self.smtp_password and self.smtp_host):
            return {
                "success": False,
                "message": "SMTP not configured. Set SMTP_USER and SMTP_PASSWORD secrets.",
            }
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                server.login(self.smtp_user, self.smtp_password)
            return {
                "success": True,
                "message": f"Connected to SMTP {self.smtp_host}:{self.smtp_port} as {self.smtp_user}",
            }
        except smtplib.SMTPAuthenticationError as e:
            detail = e.smtp_error.decode("utf-8", "replace") if isinstance(e.smtp_error, (bytes, bytearray)) else str(e.smtp_error)
            return {
                "success": False,
                "message": f"SMTP auth failed: {detail}. For Gmail, you need a Google App Password (16 chars), not your account password.",
            }
        except (OSError, smtplib.SMTPException) as e:
            return {"success": False, "message": f"SMTP error: {e}"}

    def send_email(self, to_email: str, subject: str, html_content: str,
                   plain_text: str = None, reply_to: str = None, to_name: str = None) -> dict:
        """Dispatch to the configured transport.

        Returns ``{"success": bool, "message": str, "message_id"?: str,
        "sent_at"?: ISO-8601}``. Never raises — failures come back in
        the dict so the caller can record them on the EmailSend row.
        """
        if not self.is_configured():
            if self.transport == self.TRANSPORT_SMTP:
                return {
                    "success": False,
                    "message": "SMTP not configured. Set SMTP_USER and SMTP_PASSWORD secrets.",
                }
            return {
                "success": False,
                "message": "Gmail API not configured. Set GMAIL_REFRESH_TOKEN in HF Space secrets.",
            }

        # Build the MIME envelope once; both transports use it.
        try:
            msg = self._build_mime_message(
                to_email=to_email, subject=subject, html_content=html_content,
                plain_text=plain_text, reply_to=reply_to, to_name=to_name,
            )
        except Exception as e:
            return {"success": False, "message": f"Failed to build message: {e}"}

        if self.transport == self.TRANSPORT_SMTP:
            return self._send_via_smtp(to_email, msg)
        return self._send_via_gmail_api(to_email, msg)

    def _build_mime_message(
        self, *, to_email: str, subject: str, html_content: str,
        plain_text: str | None, reply_to: str | None, to_name: str | None,
    ) -> MIMEMultipart:
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
        return msg

    def _send_via_gmail_api(self, to_email: str, msg: MIMEMultipart) -> dict:
        try:
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
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
            error = response.json().get("error", {}).get("message", response.text)
            return {"success": False, "message": f"Gmail API error: {error}"}
        except Exception as e:
            return {"success": False, "message": f"Failed: {e}"}

    def _send_via_smtp(self, to_email: str, msg: MIMEMultipart) -> dict:
        """Send via SMTP STARTTLS. Honors `SMTP_FROM_EMAIL` literally —
        the From header is preserved end-to-end (unlike Gmail API which
        rewrites it to the OAuth account)."""
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                server.login(self.smtp_user, self.smtp_password)
                # send_message uses msg["From"] / msg["To"] directly.
                server.send_message(msg)
            return {
                "success": True,
                "message": f"Sent to {to_email} via SMTP",
                "message_id": msg["Message-ID"],
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        except smtplib.SMTPAuthenticationError as e:
            detail = (
                e.smtp_error.decode("utf-8", "replace")
                if isinstance(e.smtp_error, (bytes, bytearray))
                else str(e.smtp_error)
            )
            log.warning("SMTP auth failed: %s", detail)
            return {
                "success": False,
                "message": (
                    f"SMTP auth failed: {detail}. For Gmail, use a Google "
                    "App Password (16 chars) — not your regular password."
                ),
            }
        except smtplib.SMTPRecipientsRefused as e:
            return {"success": False, "message": f"Recipient refused: {e.recipients}"}
        except smtplib.SMTPException as e:
            return {"success": False, "message": f"SMTP error: {e}"}
        except (OSError, TimeoutError) as e:
            return {"success": False, "message": f"SMTP network error: {e}"}
        except Exception as e:
            return {"success": False, "message": f"SMTP failed: {e}"}

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
        """Make HTML email-client friendly.

        Strips any ``@import url(...)`` lines from inline ``<style>`` blocks
        (Gmail strips them anyway, and Outlook chokes on them) BUT keeps
        the rest of the ``<style>`` block intact so the layout-critical
        ``img {display:block;border:0}`` and ``table {border-collapse}``
        rules continue to apply.
        """
        html_content = re.sub(r"@import\s+url\([^)]+\);?\s*", "", html_content)
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
