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


def _claim_due_rows(db, model):  # type: ignore[no-untyped-def]
    """Atomically claim every due 'scheduled' row of `model`.

    Single transaction:
      1. SELECT ... WHERE status='scheduled' FOR UPDATE SKIP LOCKED
      2. flip claimed rows to status='sending'
      3. commit

    SKIP LOCKED ensures two concurrent ticks (or future replicas) never
    fight over the same row — review fix #1. SQLite ignores the FOR
    UPDATE clause but the surrounding BEGIN..COMMIT still serializes
    writes, which is sufficient for the single-threaded SQLite case.

    Returns the list of (id, name, template_id, segment_id, ...)
    snapshots — caller iterates without holding the session open.
    """
    from sqlalchemy.exc import OperationalError

    is_sqlite = db.bind.dialect.name == "sqlite" if db.bind else False

    try:
        q = db.query(model).filter(model.status == "scheduled")
        if not is_sqlite:
            q = q.with_for_update(skip_locked=True)
        rows = q.all()
    except OperationalError:
        # SQLite without WAL or some other lock issue — fall back to
        # a plain SELECT. The single-threaded scheduler doesn't have
        # the contention this guards against anyway.
        rows = db.query(model).filter(model.status == "scheduled").all()

    claimed: list[dict] = []
    for r in rows:
        if not _is_due(getattr(r, "scheduled_at", None)):
            continue
        r.status = "sending"
        # Snapshot the columns we'll need outside the session.
        snap = {
            "id": r.id,
            "name": r.name,
            "segment_id": r.segment_id,
        }
        if model is Broadcast:
            snap["template_id"] = r.template_id or ""
        else:
            snap["template_slug"] = r.template_slug or ""
            snap["subject"] = r.subject or ""
            # Phase 7.2b: carry typed variables through to the engine so
            # scheduled emails render the same as Send Now would have.
            snap["variables"] = dict(getattr(r, "variables", None) or {})
        claimed.append(snap)
    db.commit()
    return claimed


def _fire_wa(snap: dict) -> None:
    """Run a claimed WA broadcast (already in status='sending')."""
    db = get_db()
    try:
        try:
            send_broadcast(
                db=db,
                name=snap["name"],
                channel="whatsapp",
                template_id=snap["template_id"],
                filters=BroadcastFilters(segment_id=snap["segment_id"]),
                subject="",
            )
        except Exception as e:
            _log.exception("scheduled WA broadcast %s failed: %s", snap["id"], e)
            live = db.query(Broadcast).filter(Broadcast.id == snap["id"]).first()
            if live is not None:
                live.status = "failed"
                db.commit()
    finally:
        db.close()


def _fire_email(snap: dict) -> None:
    """Run a claimed email broadcast (already in status='sending')."""
    db = get_db()
    try:
        try:
            send_broadcast(
                db=db,
                name=snap["name"],
                channel="email",
                template_id=snap["template_slug"],
                filters=BroadcastFilters(segment_id=snap["segment_id"]),
                subject=snap["subject"],
                extra_vars=dict(snap.get("variables") or {}),
            )
        except Exception as e:
            _log.exception("scheduled email broadcast %s failed: %s", snap["id"], e)
            live = db.query(Campaign).filter(Campaign.id == snap["id"]).first()
            if live is not None:
                live.status = "failed"
                db.commit()
    finally:
        db.close()


def tick_once() -> dict:
    """Single scheduler pass — fire any due rows. Returns counts so the
    test suite can assert behavior without spawning the loop.

    Review fix #1: claims are atomic per-row (FOR UPDATE SKIP LOCKED on
    Postgres). Two concurrent ticks would each pick up disjoint rows.
    """
    db = get_db()
    try:
        wa_claimed = _claim_due_rows(db, Broadcast)
        em_claimed = _claim_due_rows(db, Campaign)
    finally:
        db.close()

    for snap in wa_claimed:
        _fire_wa(snap)
    for snap in em_claimed:
        _fire_email(snap)

    return {"fired_wa": len(wa_claimed), "fired_email": len(em_claimed)}


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
