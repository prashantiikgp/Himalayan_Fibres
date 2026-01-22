"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    environment: Literal["development", "production"] = "development"
    secret_key: str = "change-me-in-production"
    debug: bool = True

    # Email (Gmail SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    smtp_from_name: str = "Himalayan Fibers"
    smtp_use_tls: bool = True

    # Database
    database_url: str
    database_url_sync: str | None = None

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Wix
    wix_webhook_public_key: str | None = None
    wix_account_id: str | None = None
    wix_site_id: str | None = None

    # Content Generation
    tavily_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Rate Limits
    email_daily_limit: int = 500
    email_rate_limit_per_minute: int = 20
    campaign_batch_size: int = 50
    campaign_batch_delay_seconds: int = 60

    # Cart Abandonment Delays (seconds)
    cart_abandoned_delay_1h: int = 3600
    cart_abandoned_delay_24h: int = 86400
    cart_abandoned_delay_72h: int = 259200

    # Webhook
    webhook_base_url: str = "http://localhost:8000"

    @property
    def smtp_from_email(self) -> str:
        """Full from email with name."""
        return f"{self.smtp_from_name} <{self.smtp_user}>"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
