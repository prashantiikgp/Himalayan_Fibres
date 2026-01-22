"""Email sending service using Gmail SMTP."""

import asyncio
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailService:
    """Service for sending emails via Gmail SMTP."""

    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.username = settings.smtp_user
        self.password = settings.smtp_password
        self.from_name = settings.smtp_from_name
        self.use_tls = settings.smtp_use_tls

    @property
    def from_email(self) -> str:
        """Get the formatted from email address."""
        return f"{self.from_name} <{self.username}>"

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_text_content: str | None = None,
        reply_to: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Send an email via SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_content: HTML email body
            plain_text_content: Plain text alternative (optional)
            reply_to: Reply-to address (optional)
            headers: Additional headers (optional)

        Returns:
            dict with status and message_id
        """
        # Create multipart message
        message = MIMEMultipart("alternative")
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = subject

        if reply_to:
            message["Reply-To"] = reply_to

        # Add custom headers
        if headers:
            for key, value in headers.items():
                message[key] = value

        # Add plain text part (fallback)
        if plain_text_content:
            plain_part = MIMEText(plain_text_content, "plain", "utf-8")
            message.attach(plain_part)

        # Add HTML part
        html_part = MIMEText(html_content, "html", "utf-8")
        message.attach(html_part)

        try:
            # Create SSL context
            context = ssl.create_default_context()

            # Connect and send
            async with aiosmtplib.SMTP(
                hostname=self.host,
                port=self.port,
                start_tls=self.use_tls,
                tls_context=context,
            ) as smtp:
                await smtp.login(self.username, self.password)
                result = await smtp.send_message(message)

            logger.info(
                "Email sent successfully",
                to=to_email,
                subject=subject,
            )

            return {
                "status": "sent",
                "to_email": to_email,
                "message_id": message.get("Message-ID"),
            }

        except aiosmtplib.SMTPAuthenticationError as e:
            logger.error(
                "SMTP authentication failed",
                error=str(e),
                to=to_email,
            )
            return {
                "status": "failed",
                "error": "Authentication failed. Check your Gmail App Password.",
                "to_email": to_email,
            }

        except aiosmtplib.SMTPRecipientsRefused as e:
            logger.error(
                "Recipient refused",
                error=str(e),
                to=to_email,
            )
            return {
                "status": "bounced",
                "error": f"Recipient refused: {to_email}",
                "to_email": to_email,
            }

        except Exception as e:
            logger.error(
                "Email send failed",
                error=str(e),
                to=to_email,
            )
            return {
                "status": "failed",
                "error": str(e),
                "to_email": to_email,
            }

    async def send_batch(
        self,
        emails: list[dict[str, Any]],
        delay_between: float = 1.0,
    ) -> list[dict[str, Any]]:
        """
        Send multiple emails with rate limiting.

        Args:
            emails: List of email dicts with to_email, subject, html_content, etc.
            delay_between: Delay between sends in seconds (for rate limiting)

        Returns:
            List of results for each email
        """
        results = []

        for i, email_data in enumerate(emails):
            result = await self.send_email(
                to_email=email_data["to_email"],
                subject=email_data["subject"],
                html_content=email_data["html_content"],
                plain_text_content=email_data.get("plain_text_content"),
                reply_to=email_data.get("reply_to"),
                headers=email_data.get("headers"),
            )
            results.append(result)

            # Rate limiting delay (except for last email)
            if i < len(emails) - 1:
                await asyncio.sleep(delay_between)

        return results

    async def verify_connection(self) -> dict[str, Any]:
        """
        Verify SMTP connection and credentials.

        Returns:
            dict with status and message
        """
        try:
            context = ssl.create_default_context()

            async with aiosmtplib.SMTP(
                hostname=self.host,
                port=self.port,
                start_tls=self.use_tls,
                tls_context=context,
            ) as smtp:
                await smtp.login(self.username, self.password)

            logger.info("SMTP connection verified")
            return {
                "status": "success",
                "message": "SMTP connection and authentication successful",
                "host": self.host,
                "username": self.username,
            }

        except aiosmtplib.SMTPAuthenticationError:
            return {
                "status": "failed",
                "message": "Authentication failed. Check your Gmail App Password.",
            }

        except Exception as e:
            return {
                "status": "failed",
                "message": f"Connection failed: {str(e)}",
            }


# Singleton instance
email_service = EmailService()
