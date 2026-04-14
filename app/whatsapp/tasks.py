"""WhatsApp Celery tasks for background processing.

Tasks:
- send_wa_text_message: Send a text message asynchronously
- send_wa_template_message: Send a template message asynchronously
- sync_wa_templates: Sync templates from Meta API to database
- download_wa_media: Download inbound media to local storage
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.whatsapp.config import wa_config

import logging

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Async engine for Celery tasks (separate from FastAPI's engine)
# ------------------------------------------------------------------

_engine = None
_session_maker = None


def _get_session() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_maker
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url, pool_pre_ping=True, pool_size=5
        )
        _session_maker = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _session_maker


def _run_async(coro):
    """Run async coroutine in a new event loop (Celery compatibility)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ==================================================================
# TASKS
# ==================================================================


@shared_task(bind=True, max_retries=3)
def send_wa_text_message(self, contact_id: int, text: str, chat_id: int):
    """Send a WhatsApp text message via Celery."""
    return _run_async(_send_wa_text(self, contact_id, text, chat_id))


async def _send_wa_text(task, contact_id: int, text: str, chat_id: int):
    from app.db.models import Contact
    from app.whatsapp.models import WAChat, WAMessage, WAMessageDirection, WAMessageStatus
    from app.whatsapp.service import whatsapp_service

    session_maker = _get_session()
    async with session_maker() as db:
        try:
            contact = await db.get(Contact, contact_id)
            chat = await db.get(WAChat, chat_id)
            if not contact or not chat:
                return {"status": "failed", "error": "Contact or chat not found"}

            to_phone = contact.wa_id or contact.phone
            if not to_phone:
                return {"status": "failed", "error": "No phone number"}

            # Create message record
            now = datetime.now(timezone.utc)
            message = WAMessage(
                chat_id=chat_id,
                contact_id=contact_id,
                direction=WAMessageDirection.OUTBOUND,
                status=WAMessageStatus.QUEUED,
                text=text,
            )
            db.add(message)
            await db.flush()

            # Send via API
            ok, wa_msg_id, error = await whatsapp_service.send_text(to_phone, text)

            if ok:
                message.status = WAMessageStatus.SENT
                message.wa_message_id = wa_msg_id
                contact.last_wa_outbound_at = now
                chat.last_message_at = now
                chat.last_message_preview = text[:255]
            else:
                message.status = WAMessageStatus.FAILED
                message.error_detail = error

            await db.commit()

            logger.info(
                "WA text message task: contact=%d ok=%s", contact_id, ok
            )
            return {"status": "sent" if ok else "failed", "wa_message_id": wa_msg_id, "error": error}

        except Exception as e:
            logger.error("WA text message task failed: %s", e)
            await db.rollback()
            cfg = wa_config.settings.rate_limits
            raise task.retry(exc=e, countdown=cfg.retry_delay_seconds)


@shared_task(bind=True, max_retries=3)
def send_wa_template_message(
    self,
    contact_id: int,
    template_name: str,
    lang: str,
    variables: list[str],
    chat_id: int,
):
    """Send a WhatsApp template message via Celery."""
    return _run_async(
        _send_wa_template(self, contact_id, template_name, lang, variables, chat_id)
    )


async def _send_wa_template(
    task, contact_id: int, template_name: str, lang: str, variables: list[str], chat_id: int
):
    from app.db.models import Contact
    from app.whatsapp.models import WAChat, WAMessage, WAMessageDirection, WAMessageStatus
    from app.whatsapp.service import whatsapp_service

    session_maker = _get_session()
    async with session_maker() as db:
        try:
            contact = await db.get(Contact, contact_id)
            chat = await db.get(WAChat, chat_id)
            if not contact or not chat:
                return {"status": "failed", "error": "Contact or chat not found"}

            to_phone = contact.wa_id or contact.phone
            if not to_phone:
                return {"status": "failed", "error": "No phone number"}

            now = datetime.now(timezone.utc)
            message = WAMessage(
                chat_id=chat_id,
                contact_id=contact_id,
                direction=WAMessageDirection.OUTBOUND,
                status=WAMessageStatus.QUEUED,
                text=f"[template: {template_name}]",
            )
            db.add(message)
            await db.flush()

            ok, wa_msg_id, error = await whatsapp_service.send_template(
                to_phone, template_name, lang, variables or None
            )

            if ok:
                message.status = WAMessageStatus.SENT
                message.wa_message_id = wa_msg_id
                contact.last_wa_outbound_at = now
                chat.last_message_at = now
                chat.last_message_preview = f"[template: {template_name}]"
            else:
                message.status = WAMessageStatus.FAILED
                message.error_detail = error

            await db.commit()

            logger.info(
                "WA template task: contact=%d template=%s ok=%s",
                contact_id, template_name, ok,
            )
            return {"status": "sent" if ok else "failed", "wa_message_id": wa_msg_id, "error": error}

        except Exception as e:
            logger.error("WA template task failed: %s", e)
            await db.rollback()
            cfg = wa_config.settings.rate_limits
            raise task.retry(exc=e, countdown=cfg.retry_delay_seconds)


@shared_task(bind=True, max_retries=2)
def sync_wa_templates(self):
    """Sync WhatsApp templates from Meta API to database."""
    return _run_async(_sync_wa_templates(self))


async def _sync_wa_templates(task):
    from app.whatsapp.models import WATemplate
    from app.whatsapp.service import whatsapp_service

    session_maker = _get_session()
    async with session_maker() as db:
        try:
            ok, templates_data, error = await whatsapp_service.list_templates()
            if not ok:
                logger.error("Template sync failed: %s", error)
                return {"status": "failed", "error": error}

            now = datetime.now(timezone.utc)
            created = 0
            updated = 0

            for tpl in templates_data or []:
                name = tpl.get("name", "")
                language = tpl.get("language", "")
                if not name or not language:
                    continue

                result = await db.execute(
                    select(WATemplate).where(
                        WATemplate.name == name, WATemplate.language == language
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    existing.category = tpl.get("category")
                    existing.status = tpl.get("status")
                    existing.quality_score = tpl.get("quality_score")
                    existing.components = tpl.get("components", [])
                    existing.last_synced_at = now
                    existing.is_draft = False
                    existing.rejection_reason = tpl.get("rejected_reason") or ""
                    updated += 1
                else:
                    new = WATemplate(
                        name=name,
                        language=language,
                        category=tpl.get("category"),
                        status=tpl.get("status"),
                        quality_score=tpl.get("quality_score"),
                        components=tpl.get("components", []),
                        last_synced_at=now,
                        is_draft=False,
                        rejection_reason=tpl.get("rejected_reason") or "",
                    )
                    db.add(new)
                    created += 1

            await db.commit()

            logger.info(
                "Template sync: total=%d created=%d updated=%d",
                len(templates_data or []), created, updated,
            )
            return {"status": "ok", "synced": len(templates_data or []), "created": created, "updated": updated}

        except Exception as e:
            logger.error("Template sync task failed: %s", e)
            await db.rollback()
            raise task.retry(exc=e, countdown=120)


@shared_task(bind=True, max_retries=3)
def download_wa_media(self, message_id: int, media_meta_id: str):
    """Download WhatsApp media to local storage."""
    return _run_async(_download_wa_media(self, message_id, media_meta_id))


async def _download_wa_media(task, message_id: int, media_meta_id: str):
    from app.whatsapp.models import WAMessage
    from app.whatsapp.service import whatsapp_service

    session_maker = _get_session()
    media_dir = wa_config.settings.media.download_dir
    os.makedirs(media_dir, exist_ok=True)

    async with session_maker() as db:
        try:
            message = await db.get(WAMessage, message_id)
            if not message:
                return {"status": "failed", "error": "Message not found"}

            # Determine file extension from media type
            ext_map = {"image": "jpg", "document": "pdf", "audio": "ogg", "video": "mp4"}
            ext = ext_map.get(message.media_type or "", "bin")
            dest = os.path.join(media_dir, f"{media_meta_id}.{ext}")

            ok, error = await whatsapp_service.download_media(media_meta_id, dest)

            if ok:
                message.media_path = dest
                await db.commit()
                logger.info("Media downloaded: message=%d path=%s", message_id, dest)
                return {"status": "ok", "path": dest}
            else:
                logger.error("Media download failed: %s", error)
                return {"status": "failed", "error": error}

        except Exception as e:
            logger.error("Media download task failed: %s", e)
            await db.rollback()
            raise task.retry(exc=e, countdown=30)
