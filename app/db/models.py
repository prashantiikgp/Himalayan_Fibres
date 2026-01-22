"""Database models for the email marketing system."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


# ===========================================
# ENUMS
# ===========================================


class ConsentStatus(enum.Enum):
    """Contact consent status."""

    PENDING = "pending"  # Imported but not confirmed
    OPTED_IN = "opted_in"  # Explicitly opted in
    OPTED_OUT = "opted_out"  # Unsubscribed
    BOUNCED = "bounced"  # Email bounced
    COMPLAINED = "complained"  # Marked as spam


class ContactType(enum.Enum):
    """Type of contact/business."""

    CARPET_EXPORTER = "carpet_exporter"
    HANDICRAFT_EXPORTER = "handicraft_exporter"
    TEXTILE_MANUFACTURER = "textile_manufacturer"
    RETAILER = "retailer"
    DESIGNER = "designer"
    BUYER = "buyer"
    PRODUCER = "producer"
    PARTNER = "partner"
    OTHER = "other"


class CampaignStatus(enum.Enum):
    """Campaign status."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENDING = "sending"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EmailSendStatus(enum.Enum):
    """Individual email send status."""

    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    BOUNCED = "bounced"
    FAILED = "failed"
    UNSUBSCRIBED = "unsubscribed"


class EmailType(enum.Enum):
    """Type of email for lifecycle tracking."""

    # Transactional
    WELCOME = "welcome"
    ORDER_CONFIRMATION = "order_confirmation"
    SHIPPING_UPDATE = "shipping_update"
    DELIVERY_CONFIRMATION = "delivery_confirmation"
    THANK_YOU_REVIEW = "thank_you_review"

    # Abandoned Cart
    CART_ABANDONED_1H = "cart_abandoned_1h"
    CART_ABANDONED_24H = "cart_abandoned_24h"
    CART_ABANDONED_72H = "cart_abandoned_72h"

    # Nurture/Educational
    EDUCATIONAL = "educational"
    PRODUCT_UPDATE = "product_update"
    COMPANY_NEWS = "company_news"

    # Re-engagement
    RE_ENGAGEMENT_30D = "re_engagement_30d"
    RE_ENGAGEMENT_90D = "re_engagement_90d"

    # Campaign
    CAMPAIGN = "campaign"


class WebhookSource(enum.Enum):
    """Source of webhook events."""

    WIX = "wix"
    MANUAL = "manual"


# ===========================================
# MODELS
# ===========================================


class Contact(Base):
    """Contact/subscriber model."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))

    # Classification
    contact_type: Mapped[ContactType] = mapped_column(
        Enum(ContactType), default=ContactType.OTHER
    )
    tags: Mapped[list[str] | None] = mapped_column(JSONB, default=list)

    # Consent tracking
    consent_status: Mapped[ConsentStatus] = mapped_column(
        Enum(ConsentStatus), default=ConsentStatus.PENDING
    )
    consent_source: Mapped[str | None] = mapped_column(String(100))  # e.g., "excel_import", "wix_checkout"
    consent_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Engagement tracking
    last_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_email_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_email_clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_emails_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_emails_opened: Mapped[int] = mapped_column(Integer, default=0)
    total_emails_clicked: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata
    custom_fields: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    email_sends: Mapped[list["EmailSend"]] = relationship(back_populates="contact")
    orders: Mapped[list["Order"]] = relationship(back_populates="contact")
    abandoned_carts: Mapped[list["AbandonedCart"]] = relationship(back_populates="contact")

    __table_args__ = (
        Index("ix_contacts_consent_status", "consent_status"),
        Index("ix_contacts_contact_type", "contact_type"),
        Index("ix_contacts_country", "country"),
    )


class Segment(Base):
    """Contact segmentation rules."""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Rules stored as JSON
    # Example: {"contact_type": ["carpet_exporter"], "country": ["India", "Nepal"], "tags": ["premium"]}
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="segment")


class EmailTemplate(Base):
    """Email template storage."""

    __tablename__ = "email_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)  # e.g., "welcome", "cart_abandoned_1h"
    description: Mapped[str | None] = mapped_column(Text)

    # Template content
    subject_template: Mapped[str] = mapped_column(Text, nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    plain_text_content: Mapped[str | None] = mapped_column(Text)

    # Template metadata
    email_type: Mapped[EmailType] = mapped_column(Enum(EmailType), nullable=False)
    required_variables: Mapped[list[str]] = mapped_column(JSONB, default=list)  # e.g., ["first_name", "order_id"]
    category: Mapped[str | None] = mapped_column(String(100))  # e.g., "transactional", "nurture", "campaign"

    # CloudHQ imported flag
    is_cloudflare_import: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_email_templates_email_type", "email_type"),
        Index("ix_email_templates_category", "category"),
    )


class Campaign(Base):
    """Email campaign."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Campaign content
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    plain_text_content: Mapped[str | None] = mapped_column(Text)

    # Targeting
    segment_id: Mapped[int | None] = mapped_column(ForeignKey("segments.id"))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("email_templates.id"))

    # Scheduling
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus), default=CampaignStatus.DRAFT
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Analytics
    total_recipients: Mapped[int] = mapped_column(Integer, default=0)
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_delivered: Mapped[int] = mapped_column(Integer, default=0)
    total_opened: Mapped[int] = mapped_column(Integer, default=0)
    total_clicked: Mapped[int] = mapped_column(Integer, default=0)
    total_bounced: Mapped[int] = mapped_column(Integer, default=0)
    total_unsubscribed: Mapped[int] = mapped_column(Integer, default=0)

    # AI-generated content metadata
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_generation_prompt: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    segment: Mapped["Segment | None"] = relationship(back_populates="campaigns")
    email_sends: Mapped[list["EmailSend"]] = relationship(back_populates="campaign")

    __table_args__ = (
        Index("ix_campaigns_status", "status"),
        Index("ix_campaigns_scheduled_at", "scheduled_at"),
    )


class EmailSend(Base):
    """Individual email send record."""

    __tablename__ = "email_sends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Associations
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    abandoned_cart_id: Mapped[int | None] = mapped_column(ForeignKey("abandoned_carts.id"))

    # Email details
    email_type: Mapped[EmailType] = mapped_column(Enum(EmailType), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)

    # Status tracking
    status: Mapped[EmailSendStatus] = mapped_column(
        Enum(EmailSendStatus), default=EmailSendStatus.QUEUED
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255))  # ID from SMTP/provider
    error_message: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Idempotency
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Relationships
    contact: Mapped["Contact"] = relationship(back_populates="email_sends")
    campaign: Mapped["Campaign | None"] = relationship(back_populates="email_sends")
    order: Mapped["Order | None"] = relationship(back_populates="email_sends")
    abandoned_cart: Mapped["AbandonedCart | None"] = relationship(back_populates="email_sends")

    __table_args__ = (
        Index("ix_email_sends_status", "status"),
        Index("ix_email_sends_email_type", "email_type"),
        Index("ix_email_sends_contact_id", "contact_id"),
        Index("ix_email_sends_sent_at", "sent_at"),
    )


class Order(Base):
    """Order snapshot from Wix webhook."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wix_order_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Contact association
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"))
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255))

    # Order details
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(String(50), default="created")

    # Shipping
    shipping_address: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Lifecycle email tracking
    welcome_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    shipping_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    review_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Raw webhook payload
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    contact: Mapped["Contact | None"] = relationship(back_populates="orders")
    email_sends: Mapped[list["EmailSend"]] = relationship(back_populates="order")

    __table_args__ = (Index("ix_orders_wix_order_id", "wix_order_id"),)


class AbandonedCart(Base):
    """Abandoned cart tracking."""

    __tablename__ = "abandoned_carts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wix_cart_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Contact association
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"))
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Cart details
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    total_value: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    checkout_url: Mapped[str | None] = mapped_column(Text)

    # Email sequence tracking
    email_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_1h_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_24h_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_72h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_72h_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Recovery tracking
    is_recovered: Mapped[bool] = mapped_column(Boolean, default=False)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_order_id: Mapped[str | None] = mapped_column(String(255))

    # Raw webhook payload
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    abandoned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    contact: Mapped["Contact | None"] = relationship(back_populates="abandoned_carts")
    email_sends: Mapped[list["EmailSend"]] = relationship(back_populates="abandoned_cart")

    __table_args__ = (
        Index("ix_abandoned_carts_contact_email", "contact_email"),
        Index("ix_abandoned_carts_is_recovered", "is_recovered"),
    )


class WebhookEvent(Base):
    """Webhook event log for idempotency and debugging."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Event identification
    source: Mapped[WebhookSource] = mapped_column(Enum(WebhookSource), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "order_created", "cart_abandoned"
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)  # From webhook payload
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256 of payload

    # Processing status
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    process_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    # Raw payload
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_webhook_events_event_id_hash", "event_id", "payload_hash", unique=True),
        Index("ix_webhook_events_is_processed", "is_processed"),
    )


class ContentDraft(Base):
    """AI-generated content drafts for review."""

    __tablename__ = "content_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Content type
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "email", "blog"
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    # Generated content
    subject: Mapped[str | None] = mapped_column(Text)  # For emails
    body: Mapped[str] = mapped_column(Text, nullable=False)
    html_body: Mapped[str | None] = mapped_column(Text)

    # Generation metadata
    prompt_used: Mapped[str] = mapped_column(Text, nullable=False)
    research_sources: Mapped[list[str]] = mapped_column(JSONB, default=list)  # URLs used for research
    model_used: Mapped[str] = mapped_column(String(100), default="claude-3-sonnet")

    # Review workflow
    status: Mapped[str] = mapped_column(String(50), default="pending_review")  # pending_review, approved, rejected, published
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    review_notes: Mapped[str | None] = mapped_column(Text)

    # Publication
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_content_drafts_status", "status"),
        Index("ix_content_drafts_content_type", "content_type"),
    )
