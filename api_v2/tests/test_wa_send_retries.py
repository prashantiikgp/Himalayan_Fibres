"""Phase 9.1 — retry behaviour for WhatsAppSender._request_with_retry.

Mocks `httpx.request` so we can simulate transient failures without
hitting Meta. We can't use pytest-httpx because it's not in the deps;
plain unittest.mock is sufficient since `_request_with_retry` is the
only thing routing through `httpx.request`.
"""

from __future__ import annotations

import ssl
from unittest.mock import MagicMock, patch

import httpx
import pytest


def _make_response(status_code: int = 200, body: dict | None = None) -> httpx.Response:
    """Build an httpx.Response so the SUT thinks Meta replied."""
    req = httpx.Request("POST", "https://graph.facebook.com/test")
    return httpx.Response(status_code=status_code, json=body or {}, request=req)


@pytest.fixture()
def sender():
    """Fresh WhatsAppSender with the prod retry budget but a fast backoff
    so tests don't sleep for 37 seconds."""
    from services.wa_sender import WhatsAppSender

    s = WhatsAppSender()
    # Keep retry count realistic (5 attempts) but collapse sleep to 0.
    s.__class__._BACKOFF_LADDER_S = (0.0, 0.0, 0.0, 0.0)
    return s


def test_request_with_retry_succeeds_on_first_attempt(sender) -> None:
    with patch(
        "services.wa_sender.httpx.request",
        return_value=_make_response(200, {"ok": True}),
    ) as mock_req:
        r = sender._request_with_retry("GET", "https://graph.facebook.com/x")
        assert r.status_code == 200
        assert mock_req.call_count == 1


def test_request_with_retry_recovers_on_third_attempt(sender) -> None:
    """Two ConnectError failures, then success — caller never sees the failures."""
    side_effects = [
        httpx.ConnectError("first fail"),
        httpx.ConnectError("second fail"),
        _make_response(200, {"ok": True}),
    ]
    with patch("services.wa_sender.httpx.request", side_effect=side_effects) as mock_req:
        r = sender._request_with_retry("POST", "https://graph.facebook.com/y")
        assert r.status_code == 200
        assert mock_req.call_count == 3


def test_request_with_retry_raises_transient_after_exhaustion(sender) -> None:
    """All attempts fail with ConnectError → raises WhatsAppSendTransientError."""
    from services.wa_sender import WhatsAppSendTransientError

    with patch(
        "services.wa_sender.httpx.request",
        side_effect=httpx.ConnectError("dead"),
    ) as mock_req:
        with pytest.raises(WhatsAppSendTransientError) as exc_info:
            sender._request_with_retry("POST", "https://graph.facebook.com/z")
    # _MAX_RETRIES=4 means 5 total attempts.
    assert mock_req.call_count == 5
    # Original exception preserved as __cause__ (D4 in plan).
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)


def test_request_with_retry_catches_bare_ssl_error(sender) -> None:
    """Hypothesis #3 in plan: ssl.SSLError can escape unwrapped from
    some httpx versions. Our widened catch (httpx.TransportError +
    ssl.SSLError + OSError) must absorb it."""
    from services.wa_sender import WhatsAppSendTransientError

    with patch(
        "services.wa_sender.httpx.request",
        side_effect=ssl.SSLError("handshake timeout"),
    ):
        with pytest.raises(WhatsAppSendTransientError):
            sender._request_with_retry("POST", "https://graph.facebook.com/z")


def test_request_with_retry_does_not_retry_on_5xx_response(sender) -> None:
    """HTTP 503 from Meta is NOT a transient httpx error — it's a Meta
    decision and the caller's existing 132001 fallback / status-code
    handling needs to see it. Helper returns the response untouched."""
    with patch(
        "services.wa_sender.httpx.request",
        return_value=_make_response(503),
    ) as mock_req:
        r = sender._request_with_retry("POST", "https://graph.facebook.com/x")
        assert r.status_code == 503
        assert mock_req.call_count == 1


def test_send_text_propagates_transient_error_not_swallowed(sender) -> None:
    """Carve-out check: send_text's `except Exception` must NOT catch
    WhatsAppSendTransientError — the API router needs it to bubble up
    so the response is 503 retryable, not 502."""
    from services.wa_sender import WhatsAppSendTransientError

    with patch(
        "services.wa_sender.httpx.request",
        side_effect=httpx.ConnectError("dead"),
    ):
        with pytest.raises(WhatsAppSendTransientError):
            sender.send_text("919999999999", "hi")


def test_submit_template_does_not_retry(sender) -> None:
    """Carve-out check: create_template (submit) is NOT routed through
    _request_with_retry. A single transient failure must surface
    immediately so we don't double-create at Meta."""
    # create_template uses raw httpx.post (not httpx.request) — patching
    # httpx.post separately to confirm only ONE call happens.
    with patch(
        "services.wa_sender.httpx.post",
        side_effect=httpx.ConnectError("dead"),
    ) as mock_post:
        ok, data, err = sender.create_template(
            name="x", category="MARKETING", language="en", components=[],
        )
        assert ok is False
        assert mock_post.call_count == 1  # NOT retried.
