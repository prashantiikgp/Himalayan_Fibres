"""
CSV-based data models for the email marketing system.
Lightweight alternative to PostgreSQL for small-scale operations.

Customer Categories:
1. EXISTING_CLIENT - Current customers you're actively doing business with
2. POTENTIAL_B2B - Carpet exporters, handicraft exporters (domestic & international)
3. YARN_STORE - Retail/wholesale yarn stores

Segmentation allows targeted campaigns instead of generic blasts.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import csv
import json
import uuid


# ===========================================
# ENUMS FOR CATEGORIZATION
# ===========================================

class CustomerType(str, Enum):
    """Primary customer categorization."""
    EXISTING_CLIENT = "existing_client"      # Active buyers, current business relationships
    POTENTIAL_B2B = "potential_b2b"          # Carpet/handicraft exporters to convert
    YARN_STORE = "yarn_store"                # Retail/wholesale yarn stores
    OTHER = "other"


class CustomerSubType(str, Enum):
    """Secondary categorization for more targeted campaigns."""
    # For EXISTING_CLIENT
    REGULAR_BUYER = "regular_buyer"          # Frequent orders
    OCCASIONAL_BUYER = "occasional_buyer"    # Infrequent orders
    VIP = "vip"                              # High-value customers

    # For POTENTIAL_B2B
    CARPET_EXPORTER = "carpet_exporter"
    HANDICRAFT_EXPORTER = "handicraft_exporter"
    TEXTILE_MANUFACTURER = "textile_manufacturer"
    IMPORTER = "importer"                    # Foreign buyers/importers

    # For YARN_STORE
    RETAIL_STORE = "retail_store"
    WHOLESALE_STORE = "wholesale_store"
    ONLINE_STORE = "online_store"

    # Generic
    OTHER = "other"


class Geography(str, Enum):
    """Geographic segmentation."""
    DOMESTIC_INDIA = "domestic_india"
    INTERNATIONAL = "international"


class EngagementLevel(str, Enum):
    """How engaged is this contact?"""
    HOT = "hot"          # Recently engaged, responded, or ordered
    WARM = "warm"        # Some engagement history
    COLD = "cold"        # No recent engagement
    NEW = "new"          # Just added, no engagement yet


class ConsentStatus(str, Enum):
    """Email consent status for compliance."""
    PENDING = "pending"          # Not yet confirmed
    OPTED_IN = "opted_in"        # Explicitly consented
    OPTED_OUT = "opted_out"      # Unsubscribed
    BOUNCED = "bounced"          # Email bounced


class CampaignStatus(str, Enum):
    """Campaign lifecycle status."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    CANCELLED = "cancelled"


class EmailSendStatus(str, Enum):
    """Individual email send status."""
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    FAILED = "failed"


# ===========================================
# DATA MODELS
# ===========================================

@dataclass
class Contact:
    """
    Contact/subscriber model.

    This is the core entity - each row represents a person/company you can email.
    """
    # Unique identifier
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Contact information
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    phone: str = ""
    website: str = ""

    # Address
    address: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    postal_code: str = ""

    # Categorization (THE KEY FIELDS FOR SEGMENTATION)
    customer_type: str = CustomerType.OTHER.value
    customer_subtype: str = CustomerSubType.OTHER.value
    geography: str = Geography.DOMESTIC_INDIA.value
    engagement_level: str = EngagementLevel.NEW.value

    # Tags for flexible filtering (comma-separated)
    # e.g., "wool,premium,trade-show-2024"
    tags: str = ""

    # Consent tracking
    consent_status: str = ConsentStatus.PENDING.value
    consent_source: str = ""  # e.g., "excel_import", "website", "trade_show"

    # Engagement tracking
    total_emails_sent: int = 0
    total_emails_opened: int = 0
    total_emails_clicked: int = 0
    last_email_sent_at: str = ""
    last_email_opened_at: str = ""

    # Outreach tracking (from your Excel)
    is_dispatched: bool = False
    is_contacted: bool = False
    response_notes: str = ""
    priority: str = ""  # e.g., "high", "medium", "low"

    # Metadata
    source: str = ""  # Where did this contact come from?
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def add_tag(self, tag: str) -> None:
        tags = self.tag_list
        if tag not in tags:
            tags.append(tag)
            self.tags = ",".join(tags)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Contact":
        # Handle boolean fields that might come as strings
        if isinstance(data.get("is_dispatched"), str):
            data["is_dispatched"] = data["is_dispatched"].lower() == "true"
        if isinstance(data.get("is_contacted"), str):
            data["is_contacted"] = data["is_contacted"].lower() == "true"
        # Handle int fields
        for int_field in ["total_emails_sent", "total_emails_opened", "total_emails_clicked"]:
            if int_field in data and data[int_field]:
                data[int_field] = int(data[int_field])
            else:
                data[int_field] = 0
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Segment:
    """
    A named filter for contacts.

    Segments allow you to target specific groups with campaigns.
    Rules are stored as JSON for flexibility.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""

    # Rules as JSON string
    # Example: {"customer_type": ["existing_client"], "geography": ["domestic_india"]}
    rules_json: str = "{}"

    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def rules(self) -> dict:
        return json.loads(self.rules_json) if self.rules_json else {}

    @rules.setter
    def rules(self, value: dict):
        self.rules_json = json.dumps(value)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Segment":
        if isinstance(data.get("is_active"), str):
            data["is_active"] = data["is_active"].lower() == "true"
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Campaign:
    """
    An email campaign targeting a segment.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""

    # Content
    subject: str = ""
    html_content: str = ""
    plain_text_content: str = ""
    template_slug: str = ""  # Reference to a template file

    # Targeting
    segment_id: str = ""  # Which segment to send to

    # Status
    status: str = CampaignStatus.DRAFT.value
    scheduled_at: str = ""
    sent_at: str = ""

    # Analytics
    total_recipients: int = 0
    total_sent: int = 0
    total_opened: int = 0
    total_clicked: int = 0
    total_bounced: int = 0

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Campaign":
        for int_field in ["total_recipients", "total_sent", "total_opened", "total_clicked", "total_bounced"]:
            if int_field in data and data[int_field]:
                data[int_field] = int(data[int_field])
            else:
                data[int_field] = 0
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class EmailSend:
    """
    Record of an individual email sent.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    contact_id: str = ""
    contact_email: str = ""
    campaign_id: str = ""

    subject: str = ""
    status: str = EmailSendStatus.QUEUED.value

    sent_at: str = ""
    opened_at: str = ""
    clicked_at: str = ""
    bounced_at: str = ""

    error_message: str = ""

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EmailSend":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ===========================================
# DEFAULT SEGMENTS
# ===========================================

DEFAULT_SEGMENTS = [
    {
        "name": "All Existing Clients",
        "description": "Current customers with active business relationship",
        "rules": {"customer_type": ["existing_client"]}
    },
    {
        "name": "VIP Clients",
        "description": "High-value existing customers",
        "rules": {"customer_type": ["existing_client"], "customer_subtype": ["vip"]}
    },
    {
        "name": "All Potential B2B",
        "description": "All potential B2B customers (exporters, manufacturers)",
        "rules": {"customer_type": ["potential_b2b"]}
    },
    {
        "name": "Carpet Exporters - India",
        "description": "Indian carpet exporters",
        "rules": {"customer_type": ["potential_b2b"], "customer_subtype": ["carpet_exporter"], "geography": ["domestic_india"]}
    },
    {
        "name": "Carpet Exporters - International",
        "description": "International carpet exporters/importers",
        "rules": {"customer_type": ["potential_b2b"], "customer_subtype": ["carpet_exporter", "importer"], "geography": ["international"]}
    },
    {
        "name": "Handicraft Exporters",
        "description": "Handicraft exporters (all geographies)",
        "rules": {"customer_type": ["potential_b2b"], "customer_subtype": ["handicraft_exporter"]}
    },
    {
        "name": "All Yarn Stores",
        "description": "All yarn retail and wholesale stores",
        "rules": {"customer_type": ["yarn_store"]}
    },
    {
        "name": "Wholesale Yarn Stores",
        "description": "Wholesale yarn distributors",
        "rules": {"customer_type": ["yarn_store"], "customer_subtype": ["wholesale_store"]}
    },
    {
        "name": "Hot Leads",
        "description": "Contacts with recent engagement",
        "rules": {"engagement_level": ["hot"]}
    },
    {
        "name": "Cold Contacts - Re-engagement",
        "description": "Contacts with no recent engagement",
        "rules": {"engagement_level": ["cold"]}
    },
    {
        "name": "New Contacts - Welcome",
        "description": "Recently added contacts",
        "rules": {"engagement_level": ["new"]}
    },
]
