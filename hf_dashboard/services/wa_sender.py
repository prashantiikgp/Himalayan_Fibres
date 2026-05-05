"""Sync WhatsApp Cloud API client.

Ported from app/whatsapp/service.py — async httpx → sync httpx.
"""

from __future__ import annotations

import logging
import mimetypes
import pathlib
from typing import Any

import httpx

from services.config import get_settings

_log = logging.getLogger(__name__)


def _quality_score_str(raw) -> str | None:
    """Coerce Meta's quality_score field to a plain string.

    Meta returns it as a dict like {"score": "GREEN", "date": 1776133652}
    on some API versions and as a flat string on others. Local column is
    VARCHAR(20), so normalize to just the score string.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get("score")
    return str(raw)[:20]


def _rejection_reason_str(raw) -> str:
    """Meta returns 'NONE' (the literal string) when there's no rejection.

    Treat that as empty so the UI doesn't show '🔴 NONE' on approved rows.
    """
    if not raw or raw == "NONE":
        return ""
    return str(raw)


class WhatsAppSender:
    """Sync client for the Meta WhatsApp Cloud API."""

    # HF Spaces' outbound to graph.facebook.com occasionally fails the
    # initial SSL handshake (suspected dual-stack IPv4/IPv6 oddity). A
    # bounded retry recovers transparently — set with the same defaults
    # the v1 broadcast engine had been quietly absorbing for months.
    _MAX_RETRIES = 2
    _RETRY_BACKOFF_S = 1.5

    def __init__(self):
        settings = get_settings()
        self.token = settings.wa_token
        self.phone_number_id = settings.wa_phone_number_id
        self.waba_id = settings.wa_waba_id
        self.api_version = "v21.0"
        self.graph_base = "https://graph.facebook.com"
        # Split connect/read so a slow handshake doesn't eat the whole budget.
        self._timeout = httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=5.0)

    def _post_with_retry(self, url: str, *, json: dict, json_ct: bool = True):
        """POST with bounded retries on transient connection / SSL errors.

        Retries ONLY on httpx network-layer failures (ConnectError,
        ConnectTimeout, ReadTimeout, RemoteProtocolError). HTTP error
        status codes are returned to the caller so the existing 132001
        language fallback keeps working untouched.
        """
        import time as _time

        last_exc: Exception | None = None
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                return httpx.post(
                    url,
                    headers=self._headers(json_ct=json_ct),
                    json=json,
                    timeout=self._timeout,
                )
            except (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
            ) as e:
                last_exc = e
                if attempt < self._MAX_RETRIES:
                    _log.warning(
                        "WA POST transient error (attempt %d/%d): %s",
                        attempt + 1, self._MAX_RETRIES + 1, e,
                    )
                    _time.sleep(self._RETRY_BACKOFF_S * (2 ** attempt))
                    continue
                raise
        # Defensive — loop always either returns or raises.
        raise last_exc or RuntimeError("WA POST failed without exception")

    @property
    def _messages_url(self) -> str:
        return f"{self.graph_base}/{self.api_version}/{self.phone_number_id}/messages"

    def _headers(self, json_ct: bool = True) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("WA_TOKEN not set")
        h = {"Authorization": f"Bearer {self.token}"}
        if json_ct:
            h["Content-Type"] = "application/json"
        return h

    @staticmethod
    def _extract_message_id(data: dict) -> str | None:
        return (data.get("messages") or [{}])[0].get("id")

    def send_text(self, to_phone: str, text: str) -> tuple[bool, str | None, str | None]:
        """Send a plain text message (24h window only)."""
        if not self.phone_number_id:
            return False, None, "WA_PHONE_NUMBER_ID not set"
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }
        try:
            r = self._post_with_retry(self._messages_url, json=payload)
            if r.status_code // 100 == 2:
                return True, self._extract_message_id(r.json()), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    # Language codes tried in order when Meta returns 132001 (template not
    # found in the translation). Handles mixed approvals across templates.
    _LANG_FALLBACKS = ["en", "en_US", "en_GB"]

    def send_template(
        self,
        to_phone: str,
        template_name: str,
        lang: str = "en_US",
        variables: "list[str] | list[tuple[str, str]] | None" = None,
        header_variables: "list[str] | list[tuple[str, str]] | None" = None,
    ) -> tuple[bool, str | None, str | None]:
        """Send a pre-approved template message (works outside 24h window).

        `variables` (body) and `header_variables` (header) each accept:
          - list[str]             — positional format ({{1}}, {{2}}…)
          - list[(name, value)]   — named format (e.g. {{customer_name}})

        Named vs positional is auto-detected per component: if any name is
        non-digit, the named-parameter payload is built.

        Language fallback: tries `lang` first, then en / en_US / en_GB on
        Meta error 132001 ("template not found in translation"). Logs the
        language that actually worked so the YAML can be corrected.
        """
        if not self.phone_number_id:
            return False, None, "WA_PHONE_NUMBER_ID not set"

        def _build_params(vals):
            if not vals:
                return None
            pairs: list[tuple[str, str]] = []
            for v in vals:
                if isinstance(v, tuple):
                    pairs.append((str(v[0]), str(v[1])))
                else:
                    pairs.append(("", str(v)))
            use_named = any(name and not name.isdigit() for name, _ in pairs)
            if use_named:
                return [
                    {"type": "text", "parameter_name": name, "text": value}
                    for name, value in pairs
                ]
            return [{"type": "text", "text": value} for _, value in pairs]

        components = []
        header_params = _build_params(header_variables)
        if header_params:
            components.append({"type": "header", "parameters": header_params})
        body_params = _build_params(variables)
        if body_params:
            components.append({"type": "body", "parameters": body_params})

        # Build the list of languages to attempt: primary first, then
        # unique fallbacks.
        tried: list[str] = []
        attempts: list[str] = [lang] + [l for l in self._LANG_FALLBACKS if l != lang]
        last_error: str | None = None

        for attempt_lang in attempts:
            if attempt_lang in tried:
                continue
            tried.append(attempt_lang)

            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": attempt_lang},
                    "components": components,
                },
            }
            try:
                r = self._post_with_retry(self._messages_url, json=payload)
            except Exception as e:
                return False, None, str(e)

            if r.status_code // 100 == 2:
                if attempt_lang != lang:
                    _log.warning(
                        "Template '%s' sent as '%s' but YAML says '%s' — update templates.yml",
                        template_name, attempt_lang, lang,
                    )
                return True, self._extract_message_id(r.json()), None

            last_error = f"{r.status_code}: {r.text}"
            # Only retry on 132001 "template not found in translation"
            if '"code":132001' not in r.text and "132001" not in r.text:
                return False, None, last_error

        return False, None, f"{last_error} (tried languages: {', '.join(tried)})"

    def send_media(self, to_phone: str, media_id: str, media_type: str = "image",
                   caption: str | None = None) -> tuple[bool, str | None, str | None]:
        """Send a media message."""
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
            r = self._post_with_retry(self._messages_url, json=payload)
            if r.status_code // 100 == 2:
                return True, self._extract_message_id(r.json()), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    def upload_media(self, filepath: str) -> tuple[bool, str | None, str | None]:
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
                r = httpx.post(url, headers=self._headers(json_ct=False), files=files, data=data, timeout=60)
            if r.status_code // 100 == 2:
                return True, r.json().get("id"), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    def verify_connection(self) -> dict:
        """Verify WhatsApp API connectivity."""
        if not self.phone_number_id:
            return {"ok": False, "error": "WA_PHONE_NUMBER_ID not set"}
        url = f"{self.graph_base}/{self.api_version}/{self.phone_number_id}"
        try:
            r = httpx.get(url, headers=self._headers(), timeout=self._timeout)
            if r.status_code // 100 == 2:
                data = r.json()
                return {
                    "ok": True,
                    "verified_name": data.get("verified_name"),
                    "display_phone_number": data.get("display_phone_number"),
                    "quality_rating": data.get("quality_rating"),
                }
            return {"ok": False, "error": f"{r.status_code}: {r.text}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_templates(self) -> tuple[bool, list[dict] | None, str | None]:
        """List all message templates for the WABA."""
        if not self.waba_id:
            return False, None, "WA_WABA_ID not set"
        url = f"{self.graph_base}/{self.api_version}/{self.waba_id}/message_templates"
        params = {
            "fields": "name,language,status,category,quality_score,components,rejected_reason",
            "limit": 100,
        }
        try:
            r = httpx.get(url, headers=self._headers(), params=params, timeout=self._timeout)
            if r.status_code // 100 == 2:
                return True, r.json().get("data", []), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    def create_template(
        self,
        name: str,
        category: str,
        language: str,
        components: list[dict],
    ) -> tuple[bool, dict | None, str | None]:
        """POST /{waba_id}/message_templates — submit a template for approval."""
        if not self.waba_id:
            return False, None, "WA_WABA_ID not set"
        url = f"{self.graph_base}/{self.api_version}/{self.waba_id}/message_templates"
        payload = {
            "name": name,
            "language": language,
            "category": category,
            "components": components,
        }
        try:
            r = httpx.post(url, headers=self._headers(), json=payload, timeout=self._timeout)
            if r.status_code // 100 == 2:
                return True, r.json(), None
            return False, None, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, None, str(e)

    def delete_template(self, name: str) -> tuple[bool, str | None]:
        """DELETE /{waba_id}/message_templates?name=... — remove a template."""
        if not self.waba_id:
            return False, "WA_WABA_ID not set"
        url = f"{self.graph_base}/{self.api_version}/{self.waba_id}/message_templates"
        try:
            r = httpx.delete(url, headers=self._headers(), params={"name": name}, timeout=self._timeout)
            if r.status_code // 100 == 2:
                return True, None
            return False, f"{r.status_code}: {r.text}"
        except Exception as e:
            return False, str(e)

    def sync_templates_from_meta(self, db) -> dict:
        """Pull templates from Meta and upsert into the local WATemplate table.

        Preserves drafts: any row with `is_draft=True` whose `(name, language)`
        does not appear in the Meta response is left untouched. Rows that do
        appear are promoted to `is_draft=False` and stamped with the latest
        status, quality_score, components, and rejection_reason.

        Phase 7.4: also decomposes Meta's `components` into the flat
        WATemplate columns (body_text/header_*/footer_text/buttons) so
        the dashboard preview surfaces have content without re-hitting
        Meta. The `components` column remains the source of truth; flat
        columns are a derived projection.
        """
        from datetime import datetime

        from services.models import WATemplate
        from services.wa_template_builder import decompose_components

        ok, templates_data, error = self.list_templates()
        if not ok:
            return {"ok": False, "error": error, "synced": 0, "created": 0, "updated": 0}

        now = datetime.utcnow()
        created = 0
        updated = 0

        for tpl in templates_data or []:
            name = tpl.get("name", "")
            language = tpl.get("language", "")
            if not name or not language:
                continue

            existing = (
                db.query(WATemplate)
                .filter(WATemplate.name == name, WATemplate.language == language)
                .one_or_none()
            )
            quality_score = _quality_score_str(tpl.get("quality_score"))
            rejection = _rejection_reason_str(tpl.get("rejected_reason"))
            components = tpl.get("components", []) or []
            flat = decompose_components(components)
            if existing:
                existing.category = tpl.get("category")
                existing.status = tpl.get("status")
                existing.quality_score = quality_score
                existing.components = components
                existing.last_synced_at = now
                existing.is_draft = False
                existing.rejection_reason = rejection
                existing.body_text = flat["body_text"]
                existing.header_format = flat["header_format"]
                existing.header_text = flat["header_text"]
                existing.header_asset_url = flat["header_asset_url"]
                existing.footer_text = flat["footer_text"]
                existing.buttons = flat["buttons"]
                updated += 1
            else:
                db.add(
                    WATemplate(
                        name=name,
                        language=language,
                        category=tpl.get("category"),
                        status=tpl.get("status"),
                        quality_score=quality_score,
                        components=components,
                        last_synced_at=now,
                        is_draft=False,
                        rejection_reason=rejection,
                        body_text=flat["body_text"],
                        header_format=flat["header_format"],
                        header_text=flat["header_text"],
                        header_asset_url=flat["header_asset_url"],
                        footer_text=flat["footer_text"],
                        buttons=flat["buttons"],
                    )
                )
                created += 1

        db.commit()
        return {
            "ok": True,
            "synced": len(templates_data or []),
            "created": created,
            "updated": updated,
        }
