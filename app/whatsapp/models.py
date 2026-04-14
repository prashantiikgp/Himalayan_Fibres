"""WhatsApp database models."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


# ===========================================
# ENUMS
# ===========================================


class WAMessageDirection(enum.Enum):
    """WhatsApp message direction."""

    INBOUND = "in"
    OUTBOUND = "out"


class WAMessageStatus(enum.Enum):
    """WhatsApp message delivery status."""

    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


# ===========================================
# MODELS
# ===========================================


class WAChat(Base):
    """WhatsApp conversation thread (one per contact)."""

    __tablename__ = "wa_chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Conversation state
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_preview: Mapped[str | None] = mapped_column(String(255))
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # 24-hour messaging window tracking
    window_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    contact: Mapped["Contact"] = relationship(back_populates="wa_chat")  # type: ignore[name-defined]  # noqa: F821
    messages: Mapped[list["WAMessage"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_wa_chats_last_message_at", "last_message_at"),
    )


class WAMessage(Base):
    """WhatsApp message (inbound and outbound)."""

    __tablename__ = "wa_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("wa_chats.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )

    # Message details
    direction: Mapped[WAMessageDirection] = mapped_column(
        Enum(WAMessageDirection), nullable=False
    )
    status: Mapped[WAMessageStatus] = mapped_column(
        Enum(WAMessageStatus), default=WAMessageStatus.QUEUED
    )
    text: Mapped[str] = mapped_column(Text, default="")

    # WhatsApp message ID (from Meta API)
    wa_message_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True
    )

    # Media fields
    media_type: Mapped[str | None] = mapped_column(String(20))  # image, document, audio, video
    media_id: Mapped[str | None] = mapped_column(String(128))  # Meta media ID
    media_path: Mapped[str | None] = mapped_column(String(512))  # local file path
    media_caption: Mapped[str | None] = mapped_column(Text)

    # Template reference
    wa_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("wa_templates.id", ondelete="SET NULL")
    )

    # Error tracking
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_detail: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    chat: Mapped["WAChat"] = relationship(back_populates="messages")
    contact: Mapped["Contact"] = relationship()  # type: ignore[name-defined]  # noqa: F821
    template: Mapped["WATemplate | None"] = relationship(back_populates="messages")
    status_events: Mapped[list["WAMessageStatusEvent"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_wa_messages_chat_created", "chat_id", "created_at"),
        Index("ix_wa_messages_contact_id", "contact_id"),
    )


class WATemplate(Base):
    """WhatsApp message template (synced from Meta)."""

    __tablename__ = "wa_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)  # en_US, hi, etc.
    category: Mapped[str | None] = mapped_column(String(50))  # MARKETING, UTILITY, AUTHENTICATION
    status: Mapped[str | None] = mapped_column(String(50))  # APPROVED, REJECTED, PENDING
    quality_score: Mapped[str | None] = mapped_column(String(20))  # GREEN, YELLOW, RED
    components: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, default=list)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    is_draft: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    body_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="", default="")
    header_format: Mapped[str | None] = mapped_column(String(20))
    header_asset_url: Mapped[str | None] = mapped_column(String(512))
    header_text: Mapped[str | None] = mapped_column(String(60))
    footer_text: Mapped[str | None] = mapped_column(String(60))
    buttons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="", default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta_template_id: Mapped[str | None] = mapped_column(String(64))

    # Relationships
    messages: Mapped[list["WAMessage"]] = relationship(back_populates="template")

    __table_args__ = (
        UniqueConstraint("name", "language", name="uq_wa_templates_name_lang"),
    )


class WAMessageStatusEvent(Base):
    """WhatsApp delivery status events from webhook."""

    __tablename__ = "wa_message_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("wa_messages.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # sent, delivered, read, failed
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_detail: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    message: Mapped["WAMessage"] = relationship(back_populates="status_events")

    __table_args__ = (
        Index("ix_wa_status_events_message_id", "message_id"),
    )
