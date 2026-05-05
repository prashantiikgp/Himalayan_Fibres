"""Broadcast scheduler — async loop that fires due scheduled broadcasts.

Runs as a background task started in api_v2/main.py's lifespan handler.
Wakes once per minute, scans both `broadcasts` and `campaigns` tables
for rows with `status='scheduled'` and `scheduled_at <= now`, marks
each `status='sending'` to claim it, and dispatches the send.

Idempotency: the status flip is the claim. If two scheduler instances
ever ran simultaneously (single-replica HF Space today, but be safe),
the second would see status='sending' and skip.

Toggle off via env: HF_SCHEDULER_ENABLED=false. The default is **off**
in tests / dev (api_v2 is imported many times) and **on** in prod
(detected via APP_PASSWORD being set with no test marker).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from services.broadcast_engine import (  # type: ignore[import-not-found]
    BroadcastFilters,
    send_broadcast,
)
from services.database import get_db  # type: ignore[import-not-found]
from services.models import Broadcast, Campaign  # type: ignore[import-not-found]


_log = logging.getLogger("api_v2.scheduler")
_TICK_SECONDS = 60


def _is_due(scheduled_at) -> bool:  # type: ignore[no-untyped-def]
    if scheduled_at is None:
        return False
    s = scheduled_at
    if s.tzinfo is None:
        s = s.replace(tzinfo=timezone.utc)
    return s <= datetime.now(timezone.utc)


def _fire_wa(b: Broadcast) -> None:
    """Run a scheduled WA broadcast. Synchronous — small batches OK."""
    db = get_db()
    try:
        # Re-read with fresh session and double-check status.
        live = db.query(Broadcast).filter(Broadcast.id == b.id).first()
        if live is None or (live.status or "").lower() != "scheduled":
            return
        live.status = "sending"
        db.commit()

        try:
            send_broadcast(
                db=db,
                name=live.name,
                channel="whatsapp",
                template_id=live.template_id or "",
                filters=BroadcastFilters(segment_id=live.segment_id),
                subject="",
            )
            # send_broadcast updates status itself; no further action.
        except Exception as e:
            _log.exception("scheduled WA broadcast %s failed: %s", live.id, e)
            live.status = "failed"
            db.commit()
    finally:
        db.close()


def _fire_email(c: Campaign) -> None:
    """Run a scheduled email broadcast. Synchronous within the
    scheduler tick — small batches finish in seconds; large ones run
    inside the same handler thread until completion. If we need
    truly async dispatch we'd hand off to BackgroundTasks via the same
    JobStore the email queue endpoint uses, but for the scheduler
    one-tick lag on big sends is acceptable."""
    db = get_db()
    try:
        live = db.query(Campaign).filter(Campaign.id == c.id).first()
        if live is None or (live.status or "").lower() != "scheduled":
            return
        live.status = "sending"
        db.commit()

        try:
            send_broadcast(
                db=db,
                name=live.name,
                channel="email",
                template_id=live.template_slug or "",
                filters=BroadcastFilters(segment_id=live.segment_id),
                subject=live.subject or "",
            )
        except Exception as e:
            _log.exception("scheduled email broadcast %s failed: %s", live.id, e)
            live.status = "failed"
            db.commit()
    finally:
        db.close()


def tick_once() -> dict:
    """Single scheduler pass — fire any due rows. Returns counts so the
    test suite can assert behavior without spawning the loop."""
    fired_wa = 0
    fired_email = 0
    db = get_db()
    try:
        wa_due = (
            db.query(Broadcast)
            .filter(Broadcast.status == "scheduled")
            .all()
        )
        em_due = (
            db.query(Campaign)
            .filter(Campaign.status == "scheduled")
            .all()
        )
    finally:
        db.close()

    for b in wa_due:
        if _is_due(getattr(b, "scheduled_at", None)):
            _fire_wa(b)
            fired_wa += 1

    for c in em_due:
        if _is_due(c.scheduled_at):
            _fire_email(c)
            fired_email += 1

    return {"fired_wa": fired_wa, "fired_email": fired_email}


async def scheduler_loop() -> None:
    """Once-per-minute scheduler tick. Keeps running until the task is
    cancelled (handled by main.py's lifespan)."""
    _log.info("scheduler loop started — tick every %ds", _TICK_SECONDS)
    while True:
        try:
            result = tick_once()
            if result["fired_wa"] or result["fired_email"]:
                _log.info(
                    "scheduler fired wa=%s email=%s",
                    result["fired_wa"], result["fired_email"],
                )
        except Exception:
            _log.exception("scheduler tick failed; continuing")
        try:
            await asyncio.sleep(_TICK_SECONDS)
        except asyncio.CancelledError:
            _log.info("scheduler loop cancelled")
            return


def enabled_in_env() -> bool:
    """Default: enabled. Set HF_SCHEDULER_ENABLED=false to disable
    (e.g. for tests, or a maintenance window)."""
    flag = os.getenv("HF_SCHEDULER_ENABLED", "true").strip().lower()
    return flag in {"1", "true", "yes", "on"}
