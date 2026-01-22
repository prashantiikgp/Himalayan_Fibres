"""
Email sending service for Himalayan Fibers campaigns.

This module handles:
- SMTP connection to Gmail
- Sending individual emails
- Sending batch campaigns
- Template rendering with personalization
- Email tracking and logging

Usage:
    from app.email_sender import EmailSender

    sender = EmailSender()

    # Test connection
    if sender.test_connection():
        print("SMTP connection OK!")

    # Send single email
    sender.send_email(
        to_email="test@example.com",
        subject="Test Email",
        html_content="<h1>Hello!</h1>"
    )

    # Send campaign
    sender.send_campaign(
        campaign_id="camp_001",
        template_path="templates/campaigns/b2b_introduction.html",
        contacts=contacts_list
    )
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid, formataddr
from datetime import datetime
from pathlib import Path
from typing import Optional
import time
import re
import os
import uuid

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class EmailSender:
    """
    Email sending service using Gmail SMTP.
    """

    def __init__(self):
        # SMTP Configuration from environment
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "info@himalayanfibre.com")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_name = os.getenv("SMTP_FROM_NAME", "Himalayan Fibres")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)

        # Rate limiting
        self.rate_limit_per_minute = int(os.getenv("EMAIL_RATE_LIMIT_PER_MINUTE", "20"))
        self.daily_limit = int(os.getenv("EMAIL_DAILY_LIMIT", "500"))

        # Tracking
        self.emails_sent_today = 0
        self.last_send_time = None

        # Project root for templates
        self.project_root = Path(__file__).parent.parent

    def test_connection(self) -> dict:
        """
        Test SMTP connection to Gmail.

        Returns:
            dict with 'success' boolean and 'message' string
        """
        try:
            context = ssl.create_default_context()

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.smtp_user, self.smtp_password)

            return {
                "success": True,
                "message": f"Successfully connected to {self.smtp_host}:{self.smtp_port} as {self.smtp_user}"
            }

        except smtplib.SMTPAuthenticationError as e:
            return {
                "success": False,
                "message": f"Authentication failed. Check your Gmail App Password. Error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}"
            }

    def render_template(self, template_content: str, variables: dict) -> str:
        """
        Render template with variables.

        Supports {{variable_name}} syntax.
        """
        rendered = template_content

        for key, value in variables.items():
            # Replace {{key}} with value
            pattern = r'\{\{\s*' + re.escape(key) + r'\s*\}\}'
            rendered = re.sub(pattern, str(value) if value else '', rendered)

        # Clean up any remaining unreplaced variables
        rendered = re.sub(r'\{\{[^}]*\}\}', '', rendered)

        return rendered

    def load_template(self, template_path: str) -> str:
        """Load template from file."""
        full_path = self.project_root / template_path
        if not full_path.exists():
            raise FileNotFoundError(f"Template not found: {full_path}")

        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()

    def preprocess_html_for_email(self, html_content: str) -> str:
        """
        Preprocess HTML to make it email-client friendly.

        - Removes external @import CSS (not supported by most email clients)
        - Ensures proper HTML structure
        - Inlines critical styles if needed
        """
        # Remove @import CSS rules (not supported in email clients)
        html_content = re.sub(r"@import\s+url\([^)]+\);?", "", html_content)

        # Remove <style> tags with external imports (keep inline styles)
        html_content = re.sub(
            r'<style[^>]*>[\s\S]*?@import[\s\S]*?</style>',
            '',
            html_content,
            flags=re.IGNORECASE
        )

        # Ensure we have proper HTML wrapper
        if not html_content.strip().lower().startswith('<!doctype') and not html_content.strip().lower().startswith('<html'):
            html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>
{html_content}
</body>
</html>"""

        return html_content

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_text: str = None,
        reply_to: str = None,
        to_name: str = None,
    ) -> dict:
        """
        Send a single email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML body
            plain_text: Optional plain text body (auto-generated if not provided)
            reply_to: Optional reply-to address
            to_name: Optional recipient name for proper addressing

        Returns:
            dict with 'success', 'message', and optionally 'message_id'
        """
        try:
            # Preprocess HTML for better email client compatibility
            html_content = self.preprocess_html_for_email(html_content)

            # Create message with proper MIME structure
            msg = MIMEMultipart('alternative')

            # Essential headers for deliverability
            msg['Subject'] = subject
            msg['From'] = formataddr((self.from_name, self.from_email))

            # Proper To header with name if available
            if to_name:
                msg['To'] = formataddr((to_name, to_email))
            else:
                msg['To'] = to_email

            # Required headers for proper email handling
            msg['Date'] = formatdate(localtime=True)
            msg['Message-ID'] = make_msgid(domain=self.from_email.split('@')[1])
            msg['MIME-Version'] = '1.0'

            # List-Unsubscribe header (important for bulk email deliverability)
            msg['List-Unsubscribe'] = f'<mailto:{self.from_email}?subject=Unsubscribe>'

            # Precedence header to indicate bulk mail
            msg['Precedence'] = 'bulk'

            if reply_to:
                msg['Reply-To'] = reply_to
            else:
                msg['Reply-To'] = self.from_email

            # Plain text version
            if not plain_text:
                # Strip HTML tags for plain text
                plain_text = re.sub('<[^<]+?>', '', html_content)
                plain_text = re.sub(r'\s+', ' ', plain_text).strip()
                # Limit plain text length
                if len(plain_text) > 5000:
                    plain_text = plain_text[:5000] + "..."

            # Attach parts - plain text first, then HTML (HTML takes precedence)
            part1 = MIMEText(plain_text, 'plain', 'utf-8')
            part2 = MIMEText(html_content, 'html', 'utf-8')

            msg.attach(part1)
            msg.attach(part2)

            # Send
            context = ssl.create_default_context()

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())

            self.emails_sent_today += 1
            self.last_send_time = datetime.now()

            return {
                "success": True,
                "message": f"Email sent to {to_email}",
                "message_id": msg['Message-ID'],
                "sent_at": datetime.now().isoformat()
            }

        except smtplib.SMTPRecipientsRefused as e:
            return {
                "success": False,
                "message": f"Recipient refused: {to_email}",
                "error": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to send email: {str(e)}",
                "error": str(e)
            }

    def send_test_email(self, to_email: str) -> dict:
        """
        Send a test email to verify configuration.
        """
        html_content = """
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #232323;">🎉 Test Email from Himalayan Fibres</h2>
            <p>This is a test email to verify your email configuration is working correctly.</p>
            <p><strong>Sent at:</strong> {timestamp}</p>
            <p><strong>From:</strong> {from_email}</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
            <p style="color: #666; font-size: 12px;">
                If you received this email, your SMTP configuration is working! 🚀
            </p>
        </div>
        """.format(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            from_email=self.from_email
        )

        return self.send_email(
            to_email=to_email,
            subject="✅ Test Email - Himalayan Fibres Email System",
            html_content=html_content
        )

    def send_campaign_email(
        self,
        to_email: str,
        to_name: str,
        company_name: str,
        template_path: str,
        subject: str,
        extra_variables: dict = None
    ) -> dict:
        """
        Send a campaign email with personalization.

        Args:
            to_email: Recipient email
            to_name: Recipient name (for personalization)
            company_name: Company name (for personalization)
            template_path: Path to HTML template
            subject: Email subject (can contain {{variables}})
            extra_variables: Additional variables for template

        Returns:
            dict with send result
        """
        # Load template
        template_content = self.load_template(template_path)

        # Build variables
        variables = {
            "name": to_name or "there",
            "first_name": to_name.split()[0] if to_name else "there",
            "company_name": company_name or "your company",
            "email": to_email,
        }

        if extra_variables:
            variables.update(extra_variables)

        # Render template
        html_content = self.render_template(template_content, variables)
        rendered_subject = self.render_template(subject, variables)

        return self.send_email(
            to_email=to_email,
            subject=rendered_subject,
            html_content=html_content
        )

    def send_batch_campaign(
        self,
        contacts: list,
        template_path: str,
        subject: str,
        batch_size: int = 50,
        delay_between_batches: int = 60,
        dry_run: bool = False
    ) -> dict:
        """
        Send campaign to multiple contacts with rate limiting.

        Args:
            contacts: List of Contact objects or dicts with email, first_name, company
            template_path: Path to HTML template
            subject: Email subject
            batch_size: Number of emails per batch
            delay_between_batches: Seconds to wait between batches
            dry_run: If True, don't actually send, just simulate

        Returns:
            dict with campaign results
        """
        results = {
            "total": len(contacts),
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
            "dry_run": dry_run,
            "started_at": datetime.now().isoformat(),
        }

        # Load template once
        template_content = self.load_template(template_path)

        for i, contact in enumerate(contacts):
            # Extract contact info
            if hasattr(contact, 'email'):
                email = contact.email
                name = contact.first_name or contact.full_name or ""
                company = contact.company or ""
            else:
                email = contact.get('email', '')
                name = contact.get('first_name', contact.get('name', ''))
                company = contact.get('company', '')

            # Skip placeholder emails
            if 'placeholder.local' in email:
                results["skipped"] += 1
                continue

            # Skip invalid emails
            if not email or '@' not in email:
                results["skipped"] += 1
                continue

            # Build variables
            variables = {
                "name": name or "there",
                "first_name": name.split()[0] if name else "there",
                "company_name": company or "your company",
                "email": email,
            }

            if dry_run:
                print(f"[DRY RUN] Would send to: {email} ({company})")
                results["sent"] += 1
                continue

            # Render and send
            html_content = self.render_template(template_content, variables)
            rendered_subject = self.render_template(subject, variables)

            result = self.send_email(
                to_email=email,
                subject=rendered_subject,
                html_content=html_content
            )

            if result["success"]:
                results["sent"] += 1
                print(f"✅ Sent to: {email}")
            else:
                results["failed"] += 1
                results["errors"].append({
                    "email": email,
                    "error": result.get("message", "Unknown error")
                })
                print(f"❌ Failed: {email} - {result.get('message')}")

            # Rate limiting: pause every batch_size emails
            if (i + 1) % batch_size == 0 and i + 1 < len(contacts):
                print(f"\n⏳ Batch complete ({i + 1}/{len(contacts)}). Waiting {delay_between_batches}s...")
                time.sleep(delay_between_batches)

            # Small delay between individual emails
            time.sleep(0.5)

        results["completed_at"] = datetime.now().isoformat()
        return results


# ===========================================
# CAMPAIGN DEFINITIONS
# ===========================================

CAMPAIGNS = {
    "b2b_introduction": {
        "name": "B2B Introduction - Carpet Exporters",
        "description": "Introduce Himalayan Fibres to potential B2B carpet exporters",
        "template": "templates/campaigns/b2b_introduction_carpet_exporters.html",
        "subject": "Premium Himalayan Fibers for {{company_name}}",
        "segment": "potential_b2b",
    },
    "tariff_advantage": {
        "name": "Tariff Advantage Campaign",
        "description": "Highlight domestic sourcing benefits amid tariff changes",
        "template": "templates/campaigns/tariff_advantage_campaign.html",
        "subject": "🌍 Beat Import Tariffs with Domestic Himalayan Fibers",
        "segment": "potential_b2b",
    },
    "sustainability": {
        "name": "Sustainability Compliance Campaign",
        "description": "Focus on EU/US sustainability requirements",
        "template": "templates/campaigns/sustainability_compliance_campaign.html",
        "subject": "🌱 Meet EU & US Sustainability Standards",
        "segment": "potential_b2b",
    },
}


def get_campaign_info(campaign_id: str) -> dict:
    """Get campaign configuration by ID."""
    return CAMPAIGNS.get(campaign_id)


def list_campaigns() -> list:
    """List all available campaigns."""
    return [
        {"id": k, **v}
        for k, v in CAMPAIGNS.items()
    ]
