"""SQLAlchemy models adapted for SQLite.

All JSONB fields use JSONType (Text + json.loads/dumps).
All server_default=func.now() replaced with Python-side defaults.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import TypeDecorator

Base = declarative_base()


class JSONType(TypeDecorator):
    """Store JSON as Text in SQLite, JSONB in Postgres (auto).

    Postgres returns JSONB columns already decoded as Python lists/dicts
    via psycopg2, while SQLite returns stored strings. This decoder
    accepts both — only calls json.loads on string input so already-
    decoded values pass through untouched.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)


def _utcnow():
    return datetime.now(timezone.utc)


# -- Contact --

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String(64), primary_key=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    first_name = Column(String(128), default="")
    last_name = Column(String(128), default="")
    company = Column(String(255), default="")
    phone = Column(String(32), default="")
    website = Column(String(512), default="")
    address = Column(Text, default="")
    city = Column(String(128), default="")
    state = Column(String(128), default="")
    country = Column(String(128), default="")
    postal_code = Column(String(20), default="")

    customer_type = Column(String(64), default="")
    customer_subtype = Column(String(64), default="")
    geography = Column(String(64), default="")
    engagement_level = Column(String(32), default="new")

    tags = Column(JSONType, default=list)
    consent_status = Column(String(32), default="pending")
    consent_source = Column(String(128), default="")
    lifecycle = Column(String(32), default="new_lead")

    total_emails_sent = Column(Integer, default=0)
    total_emails_opened = Column(Integer, default=0)
    total_emails_clicked = Column(Integer, default=0)
    last_email_sent_at = Column(DateTime, nullable=True)
    last_email_opened_at = Column(DateTime, nullable=True)

    is_dispatched = Column(Boolean, default=False)
    is_contacted = Column(Boolean, default=False)
    response_notes = Column(Text, default="")
    priority = Column(String(32), default="")
    source = Column(String(128), default="")
    notes = Column(Text, default="")

    # WhatsApp fields
    wa_id = Column(String(64), unique=True, nullable=True, index=True)
    wa_consent_status = Column(String(32), default="unknown")
    wa_profile_name = Column(String(255), default="")
    last_wa_inbound_at = Column(DateTime, nullable=True)
    last_wa_outbound_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# -- Segment --

class Segment(Base):
    __tablename__ = "segments"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    rules = Column(JSONType, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)


# -- EmailTemplate --

class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(128), unique=True, nullable=False)
    subject_template = Column(String(512), default="")
    html_content = Column(Text, default="")
    email_type = Column(String(64), default="campaign")
    required_variables = Column(JSONType, default=list)
    category = Column(String(64), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)


# -- Campaign --

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    subject = Column(String(512), default="")
    html_content = Column(Text, default="")
    template_slug = Column(String(128), default="")
    segment_id = Column(String(64), nullable=True)
    status = Column(String(32), default="draft")
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    total_recipients = Column(Integer, default=0)
    total_sent = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# -- EmailSend --

class EmailSend(Base):
    __tablename__ = "email_sends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String(64), nullable=False, index=True)
    contact_email = Column(String(255), default="")
    campaign_id = Column(Integer, nullable=True)
    subject = Column(String(512), default="")
    status = Column(String(32), default="queued")
    idempotency_key = Column(String(64), unique=True, nullable=True)
    error_message = Column(Text, default="")
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


# -- Flow --

class Flow(Base):
    __tablename__ = "flows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    channel = Column(String(32), default="email")  # email or whatsapp
    steps = Column(JSONType, default=list)  # [{day, template_slug, subject}, ...]
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)


# -- FlowRun --

class FlowRun(Base):
    __tablename__ = "flow_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_id = Column(Integer, ForeignKey("flows.id"), nullable=False)
    segment_id = Column(String(64), nullable=True)
    started_at = Column(DateTime, default=_utcnow)
    current_step = Column(Integer, default=0)
    next_step_at = Column(DateTime, nullable=True)
    status = Column(String(32), default="active")  # active, paused, completed, cancelled
    total_contacts = Column(Integer, default=0)
    total_sent = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)


# -- WAChat --

class WAChat(Base):
    __tablename__ = "wa_chats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String(64), unique=True, nullable=False)
    last_message_at = Column(DateTime, nullable=True)
    last_message_preview = Column(String(255), default="")
    unread_count = Column(Integer, default=0)
    is_archived = Column(Boolean, default=False)
    window_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


# -- WAMessage --

class WAMessage(Base):
    __tablename__ = "wa_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey("wa_chats.id"), nullable=False)
    contact_id = Column(String(64), nullable=False, index=True)
    direction = Column(String(8), nullable=False)  # "in" or "out"
    status = Column(String(32), default="queued")
    text = Column(Text, default="")
    wa_message_id = Column(String(128), unique=True, nullable=True)
    media_type = Column(String(20), nullable=True)
    media_id = Column(String(128), nullable=True)
    media_path = Column(String(512), nullable=True)
    media_caption = Column(Text, nullable=True)
    wa_batch_id = Column(String(64), nullable=True)  # For grouping WA campaigns
    error_code = Column(String(50), nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


# -- WATemplate --

class WATemplate(Base):
    __tablename__ = "wa_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    language = Column(String(10), default="en_US")
    category = Column(String(50), nullable=True)
    status = Column(String(50), nullable=True)
    quality_score = Column(String(20), nullable=True)
    components = Column(JSONType, default=list)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    is_draft = Column(Boolean, nullable=False, default=False)
    body_text = Column(Text, nullable=False, default="")
    header_format = Column(String(20), nullable=True)
    header_asset_url = Column(String(512), nullable=True)
    header_text = Column(String(60), nullable=True)
    footer_text = Column(String(60), nullable=True)
    buttons = Column(JSONType, nullable=False, default=list)
    variables = Column(JSONType, nullable=False, default=list)
    rejection_reason = Column(Text, nullable=False, default="")
    submitted_at = Column(DateTime, nullable=True)
    meta_template_id = Column(String(64), nullable=True)


# -- Broadcast --

class Broadcast(Base):
    __tablename__ = "broadcasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    channel = Column(String(32), nullable=False)  # "email" or "whatsapp"
    template_id = Column(String(128), default="")  # email slug or WA template name
    segment_id = Column(String(64), nullable=True)
    status = Column(String(32), default="draft")  # draft / sending / sent / failed
    total_recipients = Column(Integer, default=0)
    total_sent = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# -- ProductMedia --

class ProductMedia(Base):
    __tablename__ = "product_media"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(512), nullable=False)
    caption = Column(Text, default="")
    wa_media_id = Column(String(128), nullable=True)
    uploaded_at = Column(DateTime, default=_utcnow)

    kind = Column(String(32), nullable=False, default="product")
    public_url = Column(String(512), nullable=True)


# -- ContactInteraction --
# Timeline entries powering the Activity tab in the contact edit drawer.
# One row per meaningful event: email sent, WA sent, field edited, note
# added, tag added, segment matched, etc. Query by contact_id ordered by
# occurred_at DESC to render the activity feed.

class ContactInteraction(Base):
    __tablename__ = "contact_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String(64), ForeignKey("contacts.id"), index=True, nullable=False)
    kind = Column(String(32), nullable=False, index=True)
    summary = Column(String(255), default="")
    payload = Column(JSONType, default=dict)
    occurred_at = Column(DateTime, default=_utcnow, index=True)
    actor = Column(String(64), default="system")
    created_at = Column(DateTime, default=_utcnow)


# -- ContactNote --
# Threaded notes per contact. Replaces the single Contact.notes text field
# for all new notes. The legacy field is kept intact for back-compat.

class ContactNote(Base):
    __tablename__ = "contact_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contact_id = Column(String(64), ForeignKey("contacts.id"), index=True, nullable=False)
    body = Column(Text, nullable=False)
    author = Column(String(64), default="")
    created_at = Column(DateTime, default=_utcnow, index=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
