"""WhatsApp Cloud API client service.

Ported from /projects/whatsapp/app/services/wa.py — converted to async
and wrapped in a class-based singleton matching the email_service.py pattern.

Configuration is driven from:
- .env: credentials (WA_TOKEN, WA_PHONE_NUMBER_ID, WA_WABA_ID)
- config/whatsapp/settings.yml: behavior (timeouts, rate limits, media settings)
"""

from __future__ import annotations

import mimetypes
import pathlib
from typing import Any

import httpx

from app.core.config import settings
from app.whatsapp.config import wa_config


class WhatsAppService:
    """Async client for the Meta WhatsApp Cloud API."""

    def __init__(self) -> None:
        # Credentials from .env
        self.token = settings.wa_token
        self.phone_number_id = settings.wa_phone_number_id
        self.waba_id = settings.wa_waba_id

        # Behavior from YAML config
        cfg = wa_config.settings
        self.api_version = cfg.api.version
        self.graph_base = cfg.api.graph_base
        self._timeout = cfg.api.timeout_seconds
        self._media_timeout = cfg.api.media_timeout_seconds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _messages_url(self) -> str:
        return f"{self.graph_base}/{self.api_version}/{self.phone_number_id}/messages"

    def _headers(self, json: bool = True) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("WA_TOKEN not set")
        h: dict[str, str] = {"Authorization": f"Bearer {self.token}"}
        if json:
            h["Content-Type"] = "application/json"
        return h

    @staticmethod
    def _extract_message_id(data: dict[str, Any]) -> str | None:
        return (data.get("messages") or [{}])[0].get("id")

    # ------------------------------------------------------------------
    # Send messages
    # ------------------------------------------------------------------

    async def send_text(
        self, to_phone: str, text: str
    ) -> tuple[bool, str | None, str | None]:
        """Send a plain text message.

        Only works within the 24-hour messaging window.
        """
        if not self.phone_number_id:
            return False, None, "WA_PHONE_NUMBER_ID not set"
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    self._messages_url, headers=self._headers(), json=payload
                )
            if r.status_code // 100 == 2:
                return True, self._extract_message_id(r.json()), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    async def send_template(
        self,
        to_phone: str,
        template_name: str,
        lang: str = "en_US",
        variables: list[str] | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """Send a pre-approved template message.

        Works outside the 24-hour window (unlike free-form text).
        """
        if not self.phone_number_id:
            return False, None, "WA_PHONE_NUMBER_ID not set"
        components: list[dict[str, Any]] = []
        if variables:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": v} for v in variables],
                }
            )
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": lang},
                "components": components,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    self._messages_url, headers=self._headers(), json=payload
                )
            if r.status_code // 100 == 2:
                return True, self._extract_message_id(r.json()), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    async def send_media(
        self,
        to_phone: str,
        media_id: str,
        media_type: str = "image",
        caption: str | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """Send a media message (image, document, audio, video)."""
        if not self.phone_number_id:
            return False, None, "WA_PHONE_NUMBER_ID not set"
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": media_type,
            media_type: {"id": media_id},
        }
        if caption and media_type in {"image", "document", "video"}:
            payload[media_type]["caption"] = caption
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    self._messages_url, headers=self._headers(), json=payload
                )
            if r.status_code // 100 == 2:
                return True, self._extract_message_id(r.json()), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    # ------------------------------------------------------------------
    # Media upload / download
    # ------------------------------------------------------------------

    async def upload_media(
        self, filepath: str
    ) -> tuple[bool, str | None, str | None]:
        """Upload a file to WhatsApp and return the media_id."""
        if not self.phone_number_id:
            return False, None, "WA_PHONE_NUMBER_ID not set"
        url = f"{self.graph_base}/{self.api_version}/{self.phone_number_id}/media"
        mime, _ = mimetypes.guess_type(filepath)
        mime = mime or "application/octet-stream"
        try:
            with open(filepath, "rb") as f:
                files = {"file": (pathlib.Path(filepath).name, f, mime)}
                data = {"messaging_product": "whatsapp"}
                async with httpx.AsyncClient(timeout=self._media_timeout) as client:
                    r = await client.post(
                        url, headers=self._headers(json=False), files=files, data=data
                    )
            if r.status_code // 100 == 2:
                return True, r.json().get("id"), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    async def get_media_url(
        self, media_id: str
    ) -> tuple[bool, str | None, str | None]:
        """Get the download URL for a media object."""
        url = f"{self.graph_base}/{self.api_version}/{media_id}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url, headers=self._headers())
            if r.status_code // 100 == 2:
                return True, r.json().get("url"), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    async def download_media(
        self, media_id: str, dest_path: str
    ) -> tuple[bool, str | None]:
        """Download media to a local file."""
        ok, media_url, err = await self.get_media_url(media_id)
        if not ok:
            return False, err
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.get(media_url, headers=self._headers(json=False))  # type: ignore[arg-type]
            if r.status_code // 100 != 2:
                return False, f"{r.status_code} downloading media"
            with open(dest_path, "wb") as f:
                f.write(r.content)
            return True, None
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    async def list_templates(
        self,
    ) -> tuple[bool, list[dict[str, Any]] | None, str | None]:
        """List all message templates for the WhatsApp Business Account."""
        if not self.waba_id or self.waba_id == "0":
            return False, None, "WA_WABA_ID not set"
        url = f"{self.graph_base}/{self.api_version}/{self.waba_id}/message_templates"
        params = {
            "fields": "name,language,status,category,quality_score,components",
            "limit": 100,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url, headers=self._headers(), params=params)
            if r.status_code // 100 == 2:
                return True, r.json().get("data", []), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def verify_connection(self) -> dict[str, Any]:
        """Verify WhatsApp API connectivity and return phone info."""
        if not self.phone_number_id:
            return {"ok": False, "error": "WA_PHONE_NUMBER_ID not set"}
        url = f"{self.graph_base}/{self.api_version}/{self.phone_number_id}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url, headers=self._headers())
            if r.status_code // 100 == 2:
                data = r.json()
                return {
                    "ok": True,
                    "verified_name": data.get("verified_name"),
                    "display_phone_number": data.get("display_phone_number"),
                    "quality_rating": data.get("quality_rating"),
                    "platform_type": data.get("platform_type"),
                }
            return {"ok": False, "error": f"{r.status_code}: {r.text}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# Singleton instance
whatsapp_service = WhatsAppService()
