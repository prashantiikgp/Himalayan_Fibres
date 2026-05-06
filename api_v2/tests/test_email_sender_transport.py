"""Tests for the dual-transport EmailSender (Gmail API + SMTP).

Verifies:
  - `EMAIL_TRANSPORT` env var routes to the right code path.
  - Auto-detect picks Gmail API when GMAIL_REFRESH_TOKEN is set,
    SMTP when SMTP_PASSWORD is set, Gmail API by default.
  - `is_configured` checks credentials of the active transport only.
  - `send_email` actually calls smtplib when the transport is SMTP.
  - Auth failures surface as `{"success": False, ...}` without raising.
"""

from __future__ import annotations

import os
import sys
import smtplib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HF_DASHBOARD = _REPO_ROOT / "hf_dashboard"
if _HF_DASHBOARD.exists() and str(_HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_HF_DASHBOARD))

os.environ.setdefault("APP_PASSWORD", "test_secret")


def _reset_settings_singleton():
    """`get_settings` caches; reset it so per-test env vars take effect."""
    from services import config

    config._settings = None


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    """Strip out env vars the EmailSender reads so each test starts clean."""
    for var in (
        "EMAIL_TRANSPORT",
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
        "GMAIL_REFRESH_TOKEN",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM_NAME",
        "SMTP_FROM_EMAIL",
    ):
        monkeypatch.delenv(var, raising=False)
    _reset_settings_singleton()
    yield
    _reset_settings_singleton()


# ─── transport selection ───────────────────────────────────────────────


def test_auto_picks_gmail_when_refresh_token_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GMAIL_CLIENT_ID", "id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "refresh")
    _reset_settings_singleton()

    from services.email_sender import EmailSender

    s = EmailSender()
    assert s.transport == EmailSender.TRANSPORT_GMAIL
    assert s.is_configured() is True


def test_auto_picks_smtp_when_only_smtp_creds_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_USER", "info@himalayanfibres.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password-16ch")
    _reset_settings_singleton()

    from services.email_sender import EmailSender

    s = EmailSender()
    assert s.transport == EmailSender.TRANSPORT_SMTP
    assert s.is_configured() is True


def test_explicit_transport_gmail_overrides_smtp_creds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_TRANSPORT", "gmail_api")
    monkeypatch.setenv("SMTP_USER", "x")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    # No Gmail creds → still picks gmail_api but is_configured = False.
    _reset_settings_singleton()

    from services.email_sender import EmailSender

    s = EmailSender()
    assert s.transport == EmailSender.TRANSPORT_GMAIL
    assert s.is_configured() is False


def test_explicit_transport_smtp_overrides_gmail_creds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("GMAIL_CLIENT_ID", "id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "refresh")
    # No SMTP creds → smtp transport but is_configured = False.
    _reset_settings_singleton()

    from services.email_sender import EmailSender

    s = EmailSender()
    assert s.transport == EmailSender.TRANSPORT_SMTP
    assert s.is_configured() is False


def test_no_creds_anywhere_defaults_to_gmail_with_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_settings_singleton()

    from services.email_sender import EmailSender

    s = EmailSender()
    assert s.transport == EmailSender.TRANSPORT_GMAIL
    assert s.is_configured() is False
    result = s.send_email("a@b.com", "subj", "<b>hi</b>")
    assert result["success"] is False
    assert "GMAIL_REFRESH_TOKEN" in result["message"]


# ─── SMTP send path ───────────────────────────────────────────────────


def test_send_via_smtp_calls_smtplib(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "info@himalayanfibres.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-pass")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "info@himalayanfibres.com")
    _reset_settings_singleton()

    from services.email_sender import EmailSender

    fake_server = MagicMock()
    fake_server.__enter__ = MagicMock(return_value=fake_server)
    fake_server.__exit__ = MagicMock(return_value=False)

    with patch.object(smtplib, "SMTP", return_value=fake_server) as mock_smtp:
        s = EmailSender()
        result = s.send_email(
            to_email="prashant.mine@gmail.com",
            subject="Hello from SMTP",
            html_content="<p>Hi Prashant</p>",
            to_name="Prashant",
        )

    assert result["success"] is True, result
    assert "via SMTP" in result["message"]
    assert result["message_id"]
    # Verify smtplib was driven correctly.
    mock_smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
    fake_server.starttls.assert_called_once()
    fake_server.login.assert_called_once_with("info@himalayanfibres.com", "app-pass")
    fake_server.send_message.assert_called_once()
    # The MIME message passed to send_message must have the From header
    # we configured — that's the whole reason to use SMTP.
    sent_msg = fake_server.send_message.call_args.args[0]
    assert "info@himalayanfibres.com" in sent_msg["From"]


def test_send_via_smtp_auth_failure_returns_friendly_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("SMTP_USER", "info@himalayanfibres.com")
    monkeypatch.setenv("SMTP_PASSWORD", "wrong-password")
    _reset_settings_singleton()

    from services.email_sender import EmailSender

    fake_server = MagicMock()
    fake_server.__enter__ = MagicMock(return_value=fake_server)
    fake_server.__exit__ = MagicMock(return_value=False)
    fake_server.login.side_effect = smtplib.SMTPAuthenticationError(
        535, b"Username and Password not accepted"
    )

    with patch.object(smtplib, "SMTP", return_value=fake_server):
        s = EmailSender()
        result = s.send_email("a@b.com", "subj", "<p>hi</p>")

    assert result["success"] is False
    # The hint about App Password should appear, since people often
    # confuse this with their account password.
    assert "App Password" in result["message"]


def test_send_via_smtp_network_error_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("SMTP_USER", "info@himalayanfibres.com")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    _reset_settings_singleton()

    from services.email_sender import EmailSender

    with patch.object(smtplib, "SMTP", side_effect=OSError("network down")):
        s = EmailSender()
        result = s.send_email("a@b.com", "subj", "<p>hi</p>")

    assert result["success"] is False
    assert "network down" in result["message"]
