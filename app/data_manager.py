"""
CSV-based data manager for the email marketing system.

This module handles all CRUD operations for contacts, segments, campaigns, and email sends
using CSV files instead of a database. Easy to migrate to Supabase later.

Usage:
    from app.data_manager import DataManager

    dm = DataManager()

    # Contacts
    contacts = dm.get_all_contacts()
    contact = dm.get_contact_by_email("test@example.com")
    dm.add_contact(Contact(email="new@example.com", ...))

    # Segments
    segment_contacts = dm.get_contacts_by_segment("seg_id")

    # Campaigns
    dm.add_campaign(Campaign(...))
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.data_models import (
    Contact,
    Segment,
    Campaign,
    EmailSend,
    CustomerType,
    CustomerSubType,
    Geography,
    EngagementLevel,
    DEFAULT_SEGMENTS,
)


class DataManager:
    """
    Manages all data operations using CSV files.

    Data files:
    - data/contacts.csv - All contacts/subscribers
    - data/segments.csv - Segment definitions
    - data/campaigns.csv - Campaign records
    - data/email_sends.csv - Individual email send records
    """

    def __init__(self, data_dir: str = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            # Default to project's data directory
            self.data_dir = Path(__file__).parent.parent / "data"

        self.data_dir.mkdir(parents=True, exist_ok=True)

        # File paths
        self.contacts_file = self.data_dir / "contacts.csv"
        self.segments_file = self.data_dir / "segments.csv"
        self.campaigns_file = self.data_dir / "campaigns.csv"
        self.email_sends_file = self.data_dir / "email_sends.csv"

        # Initialize files if they don't exist
        self._init_files()

    def _init_files(self):
        """Create CSV files with headers if they don't exist."""
        if not self.contacts_file.exists():
            self._write_csv(self.contacts_file, [], Contact)

        if not self.segments_file.exists():
            self._write_csv(self.segments_file, [], Segment)
            # Initialize default segments
            self._init_default_segments()

        if not self.campaigns_file.exists():
            self._write_csv(self.campaigns_file, [], Campaign)

        if not self.email_sends_file.exists():
            self._write_csv(self.email_sends_file, [], EmailSend)

    def _init_default_segments(self):
        """Create default segments for common use cases."""
        for seg_data in DEFAULT_SEGMENTS:
            segment = Segment(
                name=seg_data["name"],
                description=seg_data["description"],
                rules_json=json.dumps(seg_data["rules"])
            )
            self.add_segment(segment)

    def _read_csv(self, file_path: Path, model_class) -> list:
        """Read CSV file and return list of model instances."""
        if not file_path.exists():
            return []

        items = []
        with open(file_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    items.append(model_class.from_dict(row))
                except Exception as e:
                    print(f"Warning: Could not parse row {row}: {e}")
        return items

    def _write_csv(self, file_path: Path, items: list, model_class):
        """Write list of model instances to CSV file."""
        # Get fieldnames from the dataclass
        fieldnames = list(model_class.__dataclass_fields__.keys())

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in items:
                writer.writerow(item.to_dict())

    # ===========================================
    # CONTACTS
    # ===========================================

    def get_all_contacts(self) -> list[Contact]:
        """Get all contacts."""
        return self._read_csv(self.contacts_file, Contact)

    def get_contact_by_id(self, contact_id: str) -> Optional[Contact]:
        """Get a contact by ID."""
        contacts = self.get_all_contacts()
        for contact in contacts:
            if contact.id == contact_id:
                return contact
        return None

    def get_contact_by_email(self, email: str) -> Optional[Contact]:
        """Get a contact by email address."""
        contacts = self.get_all_contacts()
        for contact in contacts:
            if contact.email.lower() == email.lower():
                return contact
        return None

    def add_contact(self, contact: Contact) -> Contact:
        """Add a new contact. Returns the contact with ID assigned."""
        contacts = self.get_all_contacts()

        # Check for duplicate email
        existing = self.get_contact_by_email(contact.email)
        if existing:
            raise ValueError(f"Contact with email {contact.email} already exists")

        contacts.append(contact)
        self._write_csv(self.contacts_file, contacts, Contact)
        return contact

    def update_contact(self, contact: Contact) -> Contact:
        """Update an existing contact."""
        contacts = self.get_all_contacts()
        contact.updated_at = datetime.now().isoformat()

        for i, c in enumerate(contacts):
            if c.id == contact.id:
                contacts[i] = contact
                self._write_csv(self.contacts_file, contacts, Contact)
                return contact

        raise ValueError(f"Contact with ID {contact.id} not found")

    def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact by ID."""
        contacts = self.get_all_contacts()
        original_len = len(contacts)
        contacts = [c for c in contacts if c.id != contact_id]

        if len(contacts) == original_len:
            return False

        self._write_csv(self.contacts_file, contacts, Contact)
        return True

    def add_contacts_bulk(self, contacts: list[Contact], skip_duplicates: bool = True) -> dict:
        """
        Add multiple contacts at once.

        Returns:
            dict with 'added', 'skipped', 'errors' counts
        """
        existing_contacts = self.get_all_contacts()
        existing_emails = {c.email.lower() for c in existing_contacts}

        added = 0
        skipped = 0
        errors = []

        for contact in contacts:
            if contact.email.lower() in existing_emails:
                if skip_duplicates:
                    skipped += 1
                    continue
                else:
                    errors.append(f"Duplicate email: {contact.email}")
                    continue

            existing_contacts.append(contact)
            existing_emails.add(contact.email.lower())
            added += 1

        self._write_csv(self.contacts_file, existing_contacts, Contact)

        return {
            "added": added,
            "skipped": skipped,
            "errors": errors,
            "total": len(existing_contacts)
        }

    def search_contacts(
        self,
        customer_type: str = None,
        customer_subtype: str = None,
        geography: str = None,
        engagement_level: str = None,
        tags: list[str] = None,
        country: str = None,
        consent_status: str = None,
    ) -> list[Contact]:
        """
        Search contacts by various criteria.
        All criteria are AND-ed together.
        """
        contacts = self.get_all_contacts()

        results = []
        for contact in contacts:
            # Customer type filter
            if customer_type and contact.customer_type != customer_type:
                continue

            # Customer subtype filter
            if customer_subtype and contact.customer_subtype != customer_subtype:
                continue

            # Geography filter
            if geography and contact.geography != geography:
                continue

            # Engagement level filter
            if engagement_level and contact.engagement_level != engagement_level:
                continue

            # Country filter
            if country and contact.country.lower() != country.lower():
                continue

            # Consent status filter
            if consent_status and contact.consent_status != consent_status:
                continue

            # Tags filter (contact must have ALL specified tags)
            if tags:
                contact_tags = contact.tag_list
                if not all(tag in contact_tags for tag in tags):
                    continue

            results.append(contact)

        return results

    # ===========================================
    # SEGMENTS
    # ===========================================

    def get_all_segments(self) -> list[Segment]:
        """Get all segments."""
        return self._read_csv(self.segments_file, Segment)

    def get_segment_by_id(self, segment_id: str) -> Optional[Segment]:
        """Get a segment by ID."""
        segments = self.get_all_segments()
        for segment in segments:
            if segment.id == segment_id:
                return segment
        return None

    def get_segment_by_name(self, name: str) -> Optional[Segment]:
        """Get a segment by name."""
        segments = self.get_all_segments()
        for segment in segments:
            if segment.name.lower() == name.lower():
                return segment
        return None

    def add_segment(self, segment: Segment) -> Segment:
        """Add a new segment."""
        segments = self.get_all_segments()
        segments.append(segment)
        self._write_csv(self.segments_file, segments, Segment)
        return segment

    def update_segment(self, segment: Segment) -> Segment:
        """Update an existing segment."""
        segments = self.get_all_segments()

        for i, s in enumerate(segments):
            if s.id == segment.id:
                segments[i] = segment
                self._write_csv(self.segments_file, segments, Segment)
                return segment

        raise ValueError(f"Segment with ID {segment.id} not found")

    def delete_segment(self, segment_id: str) -> bool:
        """Delete a segment by ID."""
        segments = self.get_all_segments()
        original_len = len(segments)
        segments = [s for s in segments if s.id != segment_id]

        if len(segments) == original_len:
            return False

        self._write_csv(self.segments_file, segments, Segment)
        return True

    def get_contacts_by_segment(self, segment_id: str) -> list[Contact]:
        """
        Get all contacts matching a segment's rules.

        Rules format: {"field_name": ["value1", "value2"], ...}
        A contact matches if it matches ANY value for each field (OR within field, AND across fields).
        """
        segment = self.get_segment_by_id(segment_id)
        if not segment:
            raise ValueError(f"Segment with ID {segment_id} not found")

        rules = segment.rules
        if not rules:
            return []

        contacts = self.get_all_contacts()
        results = []

        for contact in contacts:
            matches = True

            for field, allowed_values in rules.items():
                if not allowed_values:
                    continue

                # Get the contact's value for this field
                contact_value = getattr(contact, field, None)

                if contact_value is None:
                    matches = False
                    break

                # Special handling for tags (comma-separated)
                if field == "tags":
                    contact_tags = contact.tag_list
                    if not any(tag in contact_tags for tag in allowed_values):
                        matches = False
                        break
                else:
                    # Check if contact's value is in allowed values
                    if contact_value not in allowed_values:
                        matches = False
                        break

            if matches:
                results.append(contact)

        return results

    def get_segment_count(self, segment_id: str) -> int:
        """Get the count of contacts in a segment."""
        return len(self.get_contacts_by_segment(segment_id))

    # ===========================================
    # CAMPAIGNS
    # ===========================================

    def get_all_campaigns(self) -> list[Campaign]:
        """Get all campaigns."""
        return self._read_csv(self.campaigns_file, Campaign)

    def get_campaign_by_id(self, campaign_id: str) -> Optional[Campaign]:
        """Get a campaign by ID."""
        campaigns = self.get_all_campaigns()
        for campaign in campaigns:
            if campaign.id == campaign_id:
                return campaign
        return None

    def add_campaign(self, campaign: Campaign) -> Campaign:
        """Add a new campaign."""
        campaigns = self.get_all_campaigns()
        campaigns.append(campaign)
        self._write_csv(self.campaigns_file, campaigns, Campaign)
        return campaign

    def update_campaign(self, campaign: Campaign) -> Campaign:
        """Update an existing campaign."""
        campaigns = self.get_all_campaigns()
        campaign.updated_at = datetime.now().isoformat()

        for i, c in enumerate(campaigns):
            if c.id == campaign.id:
                campaigns[i] = campaign
                self._write_csv(self.campaigns_file, campaigns, Campaign)
                return campaign

        raise ValueError(f"Campaign with ID {campaign.id} not found")

    def delete_campaign(self, campaign_id: str) -> bool:
        """Delete a campaign by ID."""
        campaigns = self.get_all_campaigns()
        original_len = len(campaigns)
        campaigns = [c for c in campaigns if c.id != campaign_id]

        if len(campaigns) == original_len:
            return False

        self._write_csv(self.campaigns_file, campaigns, Campaign)
        return True

    # ===========================================
    # EMAIL SENDS
    # ===========================================

    def get_all_email_sends(self) -> list[EmailSend]:
        """Get all email send records."""
        return self._read_csv(self.email_sends_file, EmailSend)

    def get_email_sends_by_campaign(self, campaign_id: str) -> list[EmailSend]:
        """Get all email sends for a campaign."""
        sends = self.get_all_email_sends()
        return [s for s in sends if s.campaign_id == campaign_id]

    def get_email_sends_by_contact(self, contact_id: str) -> list[EmailSend]:
        """Get all email sends for a contact."""
        sends = self.get_all_email_sends()
        return [s for s in sends if s.contact_id == contact_id]

    def add_email_send(self, email_send: EmailSend) -> EmailSend:
        """Record a new email send."""
        sends = self.get_all_email_sends()
        sends.append(email_send)
        self._write_csv(self.email_sends_file, sends, EmailSend)
        return email_send

    def update_email_send(self, email_send: EmailSend) -> EmailSend:
        """Update an email send record (e.g., mark as opened)."""
        sends = self.get_all_email_sends()

        for i, s in enumerate(sends):
            if s.id == email_send.id:
                sends[i] = email_send
                self._write_csv(self.email_sends_file, sends, EmailSend)
                return email_send

        raise ValueError(f"EmailSend with ID {email_send.id} not found")

    # ===========================================
    # STATISTICS
    # ===========================================

    def get_contact_stats(self) -> dict:
        """Get overview statistics for contacts."""
        contacts = self.get_all_contacts()

        stats = {
            "total": len(contacts),
            "by_customer_type": {},
            "by_geography": {},
            "by_engagement_level": {},
            "by_consent_status": {},
        }

        for contact in contacts:
            # By customer type
            ct = contact.customer_type
            stats["by_customer_type"][ct] = stats["by_customer_type"].get(ct, 0) + 1

            # By geography
            geo = contact.geography
            stats["by_geography"][geo] = stats["by_geography"].get(geo, 0) + 1

            # By engagement level
            eng = contact.engagement_level
            stats["by_engagement_level"][eng] = stats["by_engagement_level"].get(eng, 0) + 1

            # By consent status
            cs = contact.consent_status
            stats["by_consent_status"][cs] = stats["by_consent_status"].get(cs, 0) + 1

        return stats

    def get_campaign_stats(self, campaign_id: str) -> dict:
        """Get statistics for a specific campaign."""
        campaign = self.get_campaign_by_id(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign with ID {campaign_id} not found")

        sends = self.get_email_sends_by_campaign(campaign_id)

        stats = {
            "campaign_id": campaign_id,
            "campaign_name": campaign.name,
            "status": campaign.status,
            "total_sent": len([s for s in sends if s.status != "queued"]),
            "delivered": len([s for s in sends if s.status == "delivered"]),
            "opened": len([s for s in sends if s.opened_at]),
            "clicked": len([s for s in sends if s.clicked_at]),
            "bounced": len([s for s in sends if s.status == "bounced"]),
            "failed": len([s for s in sends if s.status == "failed"]),
        }

        # Calculate rates
        if stats["total_sent"] > 0:
            stats["open_rate"] = round(stats["opened"] / stats["total_sent"] * 100, 2)
            stats["click_rate"] = round(stats["clicked"] / stats["total_sent"] * 100, 2)
            stats["bounce_rate"] = round(stats["bounced"] / stats["total_sent"] * 100, 2)
        else:
            stats["open_rate"] = 0
            stats["click_rate"] = 0
            stats["bounce_rate"] = 0

        return stats


# ===========================================
# EXCEL IMPORT HELPER
# ===========================================

def import_contacts_from_excel(
    file_path: str,
    customer_type: str = CustomerType.POTENTIAL_B2B.value,
    customer_subtype: str = CustomerSubType.CARPET_EXPORTER.value,
    geography: str = Geography.DOMESTIC_INDIA.value,
    source: str = "excel_import",
    data_manager: DataManager = None,
) -> dict:
    """
    Import contacts from an Excel file (like your MailChimp export).

    Args:
        file_path: Path to Excel file
        customer_type: Default customer type to assign
        customer_subtype: Default customer subtype to assign
        geography: Default geography to assign
        source: Source identifier for tracking
        data_manager: DataManager instance (creates new one if not provided)

    Returns:
        dict with import results
    """
    import pandas as pd

    df = pd.read_excel(file_path)

    # Column mapping (handles variations in column names)
    column_map = {
        "email": ["Email address(EMAIL)", "Email", "email", "EMAIL", "email_address"],
        "first_name": ["First Name", "first_name", "FirstName", "FNAME"],
        "last_name": ["Last Name", "last_name", "LastName", "LNAME"],
        "company": ["Company Name", "company", "Company", "COMPANY"],
        "phone": ["Phone Number(PHONE)", "Phone", "phone", "PHONE"],
        "website": ["Website", "website", "URL", "url"],
        "address": ["ADDRESS", "Address", "address"],
        "city": ["City", "city", "CITY"],
        "state": ["State", "state", "STATE"],
        "country": ["Country", "country", "COUNTRY"],
        "postal_code": ["ZIP/Postal", "Zip", "zip", "postal_code", "ZIP"],
        "priority": ["Priority", "priority"],
        "is_dispatched": ["Dispatched", "dispatched"],
        "is_contacted": ["Contacted", "contacted"],
        "response_notes": ["Response", "response", "Notes", "notes"],
    }

    def get_column_value(row, field_name):
        """Get value from row using column mapping."""
        for col_name in column_map.get(field_name, []):
            if col_name in df.columns:
                value = row.get(col_name)
                if pd.notna(value):
                    return str(value).strip() if not isinstance(value, bool) else value
        return ""

    contacts = []
    for _, row in df.iterrows():
        email = get_column_value(row, "email")
        if not email:
            continue

        # Determine geography based on country
        country = get_column_value(row, "country")
        geo = geography
        if country and country.lower() not in ["india", ""]:
            geo = Geography.INTERNATIONAL.value

        contact = Contact(
            email=email,
            first_name=get_column_value(row, "first_name"),
            last_name=get_column_value(row, "last_name"),
            company=get_column_value(row, "company"),
            phone=get_column_value(row, "phone"),
            website=get_column_value(row, "website"),
            address=get_column_value(row, "address"),
            city=get_column_value(row, "city"),
            state=get_column_value(row, "state"),
            country=country,
            postal_code=get_column_value(row, "postal_code"),
            customer_type=customer_type,
            customer_subtype=customer_subtype,
            geography=geo,
            engagement_level=EngagementLevel.NEW.value,
            consent_status="pending",
            consent_source=source,
            priority=get_column_value(row, "priority") or "",
            is_dispatched=bool(get_column_value(row, "is_dispatched")),
            is_contacted=bool(get_column_value(row, "is_contacted")),
            response_notes=get_column_value(row, "response_notes"),
            source=source,
        )
        contacts.append(contact)

    # Use provided data manager or create new one
    dm = data_manager or DataManager()
    result = dm.add_contacts_bulk(contacts, skip_duplicates=True)

    return result
