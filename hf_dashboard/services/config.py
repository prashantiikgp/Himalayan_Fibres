"""Dashboard configuration — Pydantic settings from environment variables."""

from __future__ import annotations

import os
from pathlib import Path


class DashboardSettings:
    """Settings loaded from environment variables (HF Spaces Secrets)."""

    def __init__(self):
        # SMTP (Gmail)
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "info@himalayanfibre.com")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from_name = os.getenv("SMTP_FROM_NAME", "Himalayan Fibres")
        self.smtp_from_email = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)

        # WhatsApp
        self.wa_token = os.getenv("WA_TOKEN", "")
        self.wa_phone_number_id = os.getenv("WA_PHONE_NUMBER_ID", "")
        self.wa_waba_id = os.getenv("WA_WABA_ID", "")
        self.wa_app_secret = os.getenv("WA_APP_SECRET", "")
        self.wa_verify_token = os.getenv("WA_VERIFY_TOKEN", "himalayan_verify_token")

        # Rate limits
        self.email_daily_limit = int(os.getenv("EMAIL_DAILY_LIMIT", "500"))
        self.email_rate_limit_per_minute = int(os.getenv("EMAIL_RATE_LIMIT_PER_MINUTE", "20"))
        self.wa_daily_limit = int(os.getenv("WA_DAILY_LIMIT", "1000"))

        # Database — Postgres (Supabase) if DATABASE_URL is set, else local SQLite.
        # Production (HF Spaces) sets DATABASE_URL via Space Secrets, which
        # points at the Supabase project and persists across restarts.
        self.database_url = os.getenv("DATABASE_URL", "").strip() or None

        # SQLite fallback path — only used when DATABASE_URL is unset.
        if Path("/data").exists():
            default_db = "/data/email_marketing.db"
        else:
            default_db = str(Path(__file__).parent.parent / "data" / "email_marketing.db")
        self.sqlite_path = os.getenv("SQLITE_PATH", default_db)

        # Auth
        self.app_password = os.getenv("APP_PASSWORD", "")

        # Media
        self.media_path = os.getenv("MEDIA_PATH", str(Path(__file__).parent.parent / "media"))


_settings = None


def get_settings() -> DashboardSettings:
    global _settings
    if _settings is None:
        _settings = DashboardSettings()
    return _settings
