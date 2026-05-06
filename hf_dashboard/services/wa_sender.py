"""Sync WhatsApp Cloud API client.

Ported from app/whatsapp/service.py — async httpx → sync httpx.
"""

from __future__ import annotations

import logging
import mimetypes
import pathlib
import random
import ssl
import time as _time
from datetime import datetime, timezone
from typing import Any

import httpx

from services.config import get_settings

_log = logging.getLogger(__name__)


class WhatsAppSendTransientError(RuntimeError):
    """Raised when a Meta API call exhausts retries on a transient
    network/TLS failure. The API router maps this to HTTP 503 with
    `retryable: true` so the frontend can offer a Retry button.

    Preserves the original exception via `__cause__`.
    """


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
    """Sync client for the Meta WhatsApp Cloud API.

    ── Phase 9.1 audit: every Meta API call site, retry-routed or not ──
    Updated 2026-05-06. Verify against grep before changing — see
    `_request_with_retry` for the routing helper.

    | Method                       | Routes through retry? | Reason if no                                  |
    | ---------------------------- | --------------------- | --------------------------------------------- |
    | send_text                    | YES (POST)            | —                                             |
    | send_template (primary)      | YES (POST)            | —                                             |
    | send_template (lang fallback)| YES (POST)            | —                                             |
    | list_templates               | YES (GET)             | Read path, idempotent — safe to retry         |
    | get_template_details         | YES (GET)             | Read path, idempotent — safe to retry         |
    | upload_media                 | NO  (POST multipart)  | Long-running; multipart form not in helper sig |
    | submit_template_to_meta      | NO  (POST)            | Idempotency: a retry could double-create      |
    | delete_template              | NO  (DELETE)          | Idempotency: re-delete returns 404            |
    """

    # Phase 9.1: retry budget bumped from 2 → 4 (5 attempts total) with
    # explicit backoff ladder [2, 5, 10, 20]s + ±20% jitter. Total worst
    # case ~37s, well under any reasonable proxy timeout. Original 4.5s
    # budget was shorter than HF egress hiccups frequently observed.
    _MAX_RETRIES = 4
    _BACKOFF_LADDER_S = (2.0, 5.0, 10.0, 20.0)

    # In-process diagnostics — read by /api/v2/wa/diagnostics. Resets on
    # Space restart, which is fine for incident triage.
    last_send_attempt_at: datetime | None = None
    last_send_error_type: str | None = None
    last_send_error_msg: str | None = None

    def __init__(self):
        settings = get_settings()
        self.token = settings.wa_token
        self.phone_number_id = settings.wa_phone_number_id
        self.waba_id = settings.wa_waba_id
        self.api_version = "v21.0"
        self.graph_base = "https://graph.facebook.com"
        # Split connect/read so a slow handshake doesn't eat the whole budget.
        # Phase 9.1: kept generous read=30s for slow Meta endpoints
        # (template submission can take 10-15s).
        self._timeout = httpx.Timeout(connect=15.0, read=30.0, write=30.0, pool=5.0)

    @classmethod
    def _record_failure(cls, exc: Exception) -> None:
        cls.last_send_attempt_at = datetime.now(timezone.utc)
        cls.last_send_error_type = type(exc).__name__
        cls.last_send_error_msg = str(exc)[:200]

    @classmethod
    def _record_success(cls) -> None:
        cls.last_send_attempt_at = datetime.now(timezone.utc)
        cls.last_send_error_type = None
        cls.last_send_error_msg = None

    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Execute an httpx call with bounded retries on transient errors.

        Catches the entire `httpx.TransportError` family (ConnectError /
        ConnectTimeout / ReadTimeout / RemoteProtocolError + future
        siblings) plus bare `ssl.SSLError` and `OSError` (belt-and-braces:
        in some httpx/anyio versions a handshake failure can escape as
        either rather than wrapped in `httpx.ConnectError` — D2 in plan).
        HTTP error status codes are returned to the caller untouched so
        existing fallbacks (e.g. send_template's 132001 language retry)
        keep working.

        On final failure raises `WhatsAppSendTransientError` with the
        original exception preserved as `__cause__`.
        """
        kwargs.setdefault("timeout", self._timeout)
        method_upper = method.upper()
        last_exc: Exception | None = None
        started = _time.monotonic()
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                resp = httpx.request(method_upper, url, **kwargs)
                if attempt > 0:
                    _log.info(
                        "WA %s recovered on attempt %d/%d after %.1fs",
                        method_upper, attempt + 1, self._MAX_RETRIES + 1,
                        _time.monotonic() - started,
                    )
                self._record_success()
                return resp
            except (httpx.TransportError, ssl.SSLError, OSError) as e:
                last_exc = e
                if attempt < self._MAX_RETRIES:
                    backoff = self._BACKOFF_LADDER_S[
                        min(attempt, len(self._BACKOFF_LADDER_S) - 1)
                    ]
                    backoff *= 1.0 + random.uniform(-0.2, 0.2)  # ±20% jitter
                    _log.warning(
                        "WA %s transient error (attempt %d/%d, sleeping %.1fs): %s: %s",
                        method_upper, attempt + 1, self._MAX_RETRIES + 1,
                        backoff, type(e).__name__, e,
                    )
                    _time.sleep(backoff)
                    continue
                # Final attempt failed — log structured + raise wrapped.
                elapsed = _time.monotonic() - started
                _log.error(
                    "WA %s exhausted %d retries after %.1fs (timeout connect=%s read=%s); "
                    "final error %s: %s; url=%s",
                    method_upper, self._MAX_RETRIES + 1, elapsed,
                    self._timeout.connect, self._timeout.read,
                    type(e).__name__, e, url,
                )
                self._record_failure(e)
                raise WhatsAppSendTransientError(
                    f"Meta API unreachable after {self._MAX_RETRIES + 1} attempts: "
                    f"{type(e).__name__}: {e}"
                ) from e
        # Defensive — loop always either returns or raises.
        raise WhatsAppSendTransientError("unreachable") from last_exc

    # Backwards-compat shim — existing call sites still use the old name.
    def _post_with_retry(self, url: str, *, json: dict, json_ct: bool = True):
        return self._request_with_retry(
            "POST",
            url,
            headers=self._headers(json_ct=json_ct),
            json=json,
        )

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

    @staticmethod
    def _build_media_header_param(template_name: str, lang: str) -> dict | None:
        """Phase 10.2: look up the template's header_format + header_asset_url
        and return the right Meta media-parameter dict if (and only if)
        the template uses an IMAGE/VIDEO/DOCUMENT header.

        Returns None for TEXT-header or no-header templates — caller
        falls back to the existing text-parameter path.

        Importantly: returns None if `header_asset_url` is empty even
        when header_format is media — the send will then fail at Meta
        with a clear "header parameter required" error. Better than
        silently sending a bogus URL.
        """
        try:
            from services.database import get_db  # type: ignore[import-not-found]
            from services.models import WATemplate  # type: ignore[import-not-found]
        except ImportError:
            return None

        db = get_db()
        try:
            tpl = (
                db.query(WATemplate)
                .filter(
                    WATemplate.name == template_name,
                    WATemplate.language == lang,
                    WATemplate.is_draft.is_(False),
                )
                .order_by(WATemplate.id.desc())
                .first()
            )
        finally:
            db.close()

        if tpl is None:
            return None
        fmt = (tpl.header_format or "").upper()
        url = (tpl.header_asset_url or "").strip()
        if fmt not in ("IMAGE", "VIDEO", "DOCUMENT") or not url:
            return None
        media_key = fmt.lower()  # IMAGE → "image", etc.
        return {"type": media_key, media_key: {"link": url}}

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
        except WhatsAppSendTransientError:
            # Propagate so the API router can map to 503 retryable
            # instead of 502 generic. Phase 9.1.
            raise
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

        # Phase 10.2: media-header support. If the WATemplate row has
        # header_format in (IMAGE/VIDEO/DOCUMENT) AND a header_asset_url,
        # prepend a header component with the right media param. Without
        # this, Meta returns "(#100) Invalid parameter" because the
        # approved template requires a media parameter at send time.
        media_header_param = self._build_media_header_param(template_name, lang)

        components = []
        if media_header_param is not None:
            # Media header takes precedence over text — a template can't
            # have both. If both were somehow supplied, media wins (text
            # header_variables would belong to a TEXT-format template).
            components.append({"type": "header", "parameters": [media_header_param]})
        else:
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
            except WhatsAppSendTransientError:
                # Propagate so router → 503 retryable. Phase 9.1.
                raise
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
        except WhatsAppSendTransientError:
            raise
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
        """List all message templates for the WABA. (Read path; routes
        through `_request_with_retry` — Phase 9.1 audit row.)"""
        if not self.waba_id:
            return False, None, "WA_WABA_ID not set"
        url = f"{self.graph_base}/{self.api_version}/{self.waba_id}/message_templates"
        params = {
            "fields": "name,language,status,category,quality_score,components,rejected_reason",
            "limit": 100,
        }
        try:
            r = self._request_with_retry(
                "GET", url, headers=self._headers(), params=params,
            )
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
        # Phase 9.1 carve-out: NOT routed through _request_with_retry.
        # Template submission is non-idempotent — a transparent retry
        # could double-create the template at Meta. Operator handles
        # rare transient failures by clicking Submit again.
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
        # Phase 9.1 carve-out: NOT routed through retry — re-deleting
        # an already-deleted template returns 404 and breaks idempotency
        # of the operator-visible result.
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

            # Phase 9.2: tolerate duplicate (name, language) rows that
            # accumulated from earlier draft-then-submit flows. Keep
            # non-drafts ahead of drafts; oldest id wins ties.
            candidates = (
                db.query(WATemplate)
                .filter(WATemplate.name == name, WATemplate.language == language)
                .order_by(WATemplate.is_draft.asc(), WATemplate.id.asc())
                .all()
            )
            existing = candidates[0] if candidates else None
            quality_score = _quality_score_str(tpl.get("quality_score"))
            rejection = _rejection_reason_str(tpl.get("rejected_reason"))
            components = tpl.get("components", []) or []
            flat = decompose_components(components)
            if existing:
                # Sync has consolidated this template at Meta — drop any
                # remaining sibling rows so the next sync stays clean.
                for dup in candidates[1:]:
                    _log.warning(
                        "sync: removing duplicate WATemplate id=%s name=%s lang=%s is_draft=%s",
                        dup.id, dup.name, dup.language, dup.is_draft,
                    )
                    db.delete(dup)
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
