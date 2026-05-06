"""Phase 7.7 — flow engine v2 + membership endpoints + Mark Sample Shipped.

Coverage targets per PLAN_flows §8 step 9:
  - Tag-trigger creates a membership.
  - Idempotency: assigning the same (flow, contact) twice while the
    first is live is a no-op.
  - tick_flows claims due memberships and advances the state machine.
  - flow_step_runs.idempotency_key blocks double-fire even on re-claim.
  - Sample Dispatch flow is seeded with tag trigger + 3 steps.
  - "Mark sample shipped" endpoint writes tracking onto memberships.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HF_DASHBOARD = _REPO_ROOT / "hf_dashboard"
if _HF_DASHBOARD.exists() and str(_HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_HF_DASHBOARD))

os.environ.setdefault("APP_PASSWORD", "test_secret")


@pytest.fixture(autouse=True, scope="module")
def _bootstrap_db():
    """Importing `api_v2.main` triggers `ensure_db_ready` which creates
    tables + seeds Phase 7 flows. Tests that don't use the `client`
    fixture would otherwise hit the DB before tables exist."""
    from api_v2.main import app  # noqa: F401

    yield


@pytest.fixture()
def client() -> TestClient:
    from api_v2.main import app

    return TestClient(app)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test_secret"}


# ─── helpers ─────────────────────────────────────────────────────────


def _seed_contact(suffix: str | None = None, **kwargs) -> str:
    """Insert a single test contact and return its id."""
    from services.database import get_db
    from services.models import Contact

    suffix = suffix or str(int(time.time() * 1000) % 1_000_000)
    cid = f"flowtest_{suffix}"
    db = get_db()
    try:
        existing = db.query(Contact).filter(Contact.id == cid).first()
        if existing:
            return cid
        defaults = {
            "first_name": "Sample",
            "last_name": "Tester",
            "email": f"{cid}@example.com",
            "phone": "9000000000",
            "wa_id": f"91{cid[-10:]}",
            "lifecycle": "new_lead",
            "consent_status": "opted_in",
            "wa_consent_status": "opted_in",
            "tags": [],
        }
        defaults.update(kwargs)
        db.add(Contact(id=cid, **defaults))
        db.commit()
    finally:
        db.close()
    return cid


def _seed_tag_flow(tag: str) -> int:
    """Insert a test flow with a tag trigger. Returns flow id."""
    from services.database import get_db
    from services.models import Flow

    db = get_db()
    try:
        flow = Flow(
            name=f"test_flow_{tag}_{int(time.time() * 1000)}",
            slug=f"test_flow_{tag}_{int(time.time() * 1000)}",
            description="test",
            channel="email",
            trigger_type="tag",
            trigger_config={"tag": tag},
            steps=[
                {
                    "step_index": 0,
                    "channel": "email",
                    "template_slug": "welcome",
                    "delay_after_prev": {"value": 0, "unit": "days"},
                },
                {
                    "step_index": 1,
                    "channel": "email",
                    "template_slug": "welcome",
                    "delay_after_prev": {"value": 1, "unit": "days"},
                },
            ],
            is_active=True,
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)
        return flow.id
    finally:
        db.close()


# ─── trigger evaluator tests ─────────────────────────────────────────


def test_tag_trigger_creates_membership() -> None:
    from api_v2.services.flows_engine_v2 import evaluate_tag_trigger
    from services.database import get_db
    from services.models import FlowMembership

    flow_id = _seed_tag_flow("test_tag_create")
    cid = _seed_contact("tag_create")

    db = get_db()
    try:
        n = evaluate_tag_trigger(db, contact_id=cid, tag_name="test_tag_create")
        db.commit()
        assert n == 1
        members = (
            db.query(FlowMembership)
            .filter(
                FlowMembership.contact_id == cid,
                FlowMembership.flow_id == flow_id,
            )
            .all()
        )
        assert len(members) == 1
        m = members[0]
        assert m.status == "active"
        assert m.current_step_index == 0
        assert m.trigger_source == "tag"
        assert m.next_fire_at is not None
    finally:
        db.close()


def test_tag_trigger_idempotent_double_call() -> None:
    from api_v2.services.flows_engine_v2 import evaluate_tag_trigger
    from services.database import get_db
    from services.models import FlowMembership

    flow_id = _seed_tag_flow("test_tag_dup")
    cid = _seed_contact("tag_dup")

    db = get_db()
    try:
        evaluate_tag_trigger(db, contact_id=cid, tag_name="test_tag_dup")
        db.commit()
        evaluate_tag_trigger(db, contact_id=cid, tag_name="test_tag_dup")
        db.commit()
        members = (
            db.query(FlowMembership)
            .filter(
                FlowMembership.contact_id == cid,
                FlowMembership.flow_id == flow_id,
            )
            .all()
        )
        assert len(members) == 1, "second tag_added must not duplicate"
    finally:
        db.close()


def test_lifecycle_trigger_creates_membership() -> None:
    from api_v2.services.flows_engine_v2 import evaluate_lifecycle_trigger
    from services.database import get_db
    from services.models import Contact, Flow, FlowMembership

    db = get_db()
    flow_id: int
    try:
        flow = Flow(
            name=f"lc_test_{int(time.time() * 1000)}",
            slug=f"lc_test_{int(time.time() * 1000)}",
            description="lifecycle trigger test",
            channel="email",
            trigger_type="lifecycle",
            trigger_config={"to": "interested"},
            steps=[{"channel": "email", "template_slug": "welcome", "delay_after_prev": {"value": 0, "unit": "days"}}],
            is_active=True,
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)
        flow_id = flow.id
    finally:
        db.close()

    cid = _seed_contact("lifecycle_create", lifecycle="contacted")

    db = get_db()
    try:
        c = db.query(Contact).filter(Contact.id == cid).one()
        n = evaluate_lifecycle_trigger(
            db, contact=c, old_lifecycle="contacted", new_lifecycle="interested"
        )
        db.commit()
        assert n == 1
        m = (
            db.query(FlowMembership)
            .filter(
                FlowMembership.contact_id == cid, FlowMembership.flow_id == flow_id,
            )
            .one()
        )
        assert m.trigger_source == "lifecycle"
    finally:
        db.close()


def test_tag_trigger_resumes_waiting_event_membership() -> None:
    """A membership parked at status=waiting_event whose current step's
    trigger_event matches the new tag should flip back to active."""
    from api_v2.services.flows_engine_v2 import evaluate_tag_trigger
    from services.database import get_db
    from services.models import Flow, FlowMembership

    db = get_db()
    cid = _seed_contact("waiting_event")
    try:
        # A flow whose step 1 has trigger_event tag=resume_me.
        flow = Flow(
            name=f"wait_flow_{int(time.time() * 1000)}",
            slug=f"wait_flow_{int(time.time() * 1000)}",
            description="waiting-event resume test",
            channel="email",
            trigger_type="manual",
            trigger_config={},
            steps=[
                {"channel": "email", "template_slug": "welcome", "delay_after_prev": {"value": 0, "unit": "days"}},
                {
                    "channel": "email",
                    "template_slug": "welcome",
                    "trigger_event": {"type": "tag", "value": "resume_me"},
                },
            ],
            is_active=True,
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)

        member = FlowMembership(
            flow_id=flow.id,
            contact_id=cid,
            status="waiting_event",
            current_step_index=1,
            next_fire_at=None,
            trigger_source="manual",
        )
        db.add(member)
        db.commit()
        member_id = member.id

        evaluate_tag_trigger(db, contact_id=cid, tag_name="resume_me")
        db.commit()

        m = db.query(FlowMembership).filter(FlowMembership.id == member_id).one()
        assert m.status == "active"
        assert m.next_fire_at is not None
    finally:
        db.close()


# ─── tick + idempotency tests ────────────────────────────────────────


def test_tick_flows_returns_shape() -> None:
    """tick_flows is a no-op-friendly function — returns a dict with
    `claimed` and `fired` integer keys regardless of DB state."""
    from api_v2.services.flows_engine_v2 import tick_flows

    result = tick_flows()
    assert "claimed" in result and isinstance(result["claimed"], int)
    assert "fired" in result and isinstance(result["fired"], int)
    assert result["fired"] <= result["claimed"]


def test_tick_flows_advances_state_machine() -> None:
    """Mock the email sender so we don't actually call Gmail. After a
    successful step 0 fire, the membership should advance to step 1
    with next_fire_at scheduled per delay_after_prev."""
    from api_v2.services.flows_engine_v2 import tick_flows
    from services.database import get_db
    from services.models import EmailTemplate, Flow, FlowMembership, FlowStepRun

    flow_id = _seed_tag_flow("test_advance")
    cid = _seed_contact("advance")

    # Make sure the welcome template row exists in the DB so the engine
    # finds it (the seed loader creates it on first boot).
    db = get_db()
    try:
        if not db.query(EmailTemplate).filter(EmailTemplate.slug == "welcome").first():
            db.add(EmailTemplate(slug="welcome", name="Welcome", subject_template="Hi"))
            db.commit()

        # Seed a membership that's due now.
        member = FlowMembership(
            flow_id=flow_id,
            contact_id=cid,
            status="active",
            current_step_index=0,
            next_fire_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            trigger_source="manual",
        )
        db.add(member)
        db.commit()
        member_id = member.id
    finally:
        db.close()

    fake_sender = MagicMock()
    fake_sender.is_configured.return_value = True
    fake_sender.send_email.return_value = {"success": True, "message_id": "mock-msg-id"}

    with (
        patch("services.email_sender.EmailSender", return_value=fake_sender),
        patch(
            "services.email_sender.render_template_by_slug",
            return_value="<html>ok</html>",
        ),
        patch(
            "services.email_sender.render_template_string",
            return_value="rendered subject",
        ),
        patch("api_v2.services.flows_engine_v2.time.sleep"),
    ):
        result = tick_flows()

    assert result["claimed"] >= 1
    assert result["fired"] >= 1

    db = get_db()
    try:
        m = db.query(FlowMembership).filter(FlowMembership.id == member_id).one()
        assert m.current_step_index == 1, "should have advanced"
        assert m.status == "active"
        assert m.next_fire_at is not None
        # SQLite returns naive datetimes — normalize to UTC for compare.
        nfa = m.next_fire_at
        if nfa.tzinfo is None:
            nfa = nfa.replace(tzinfo=timezone.utc)
        assert nfa > datetime.now(timezone.utc)

        runs = (
            db.query(FlowStepRun)
            .filter(FlowStepRun.membership_id == member_id)
            .all()
        )
        assert any(r.step_index == 0 and r.status == "sent" for r in runs)
    finally:
        db.close()


def test_step_run_idempotency_key_blocks_double_fire() -> None:
    """Manually inserting a duplicate idempotency key should fail."""
    from sqlalchemy.exc import IntegrityError
    from services.database import get_db
    from services.models import FlowMembership, FlowStepRun

    flow_id = _seed_tag_flow("test_idem")
    cid = _seed_contact("idem")

    db = get_db()
    try:
        member = FlowMembership(
            flow_id=flow_id, contact_id=cid, status="active",
            current_step_index=0, trigger_source="manual",
        )
        db.add(member)
        db.commit()
        key = f"flowmem_{member.id}_step_0_email"

        db.add(FlowStepRun(
            membership_id=member.id, step_index=0, channel="email",
            status="sent", template_slug="welcome", idempotency_key=key,
        ))
        db.commit()

        db.add(FlowStepRun(
            membership_id=member.id, step_index=0, channel="email",
            status="sent", template_slug="welcome", idempotency_key=key,
        ))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_multi_channel_step_uses_distinct_idempotency_keys() -> None:
    """Same step_index, different channel → distinct keys, both insert."""
    from services.database import get_db
    from services.models import FlowMembership, FlowStepRun

    flow_id = _seed_tag_flow("test_multi")
    cid = _seed_contact("multi")

    db = get_db()
    try:
        member = FlowMembership(
            flow_id=flow_id, contact_id=cid, status="active",
            current_step_index=0, trigger_source="manual",
        )
        db.add(member)
        db.commit()

        db.add(FlowStepRun(
            membership_id=member.id, step_index=0, channel="email",
            status="sent", template_slug="welcome",
            idempotency_key=f"flowmem_{member.id}_step_0_email",
        ))
        db.add(FlowStepRun(
            membership_id=member.id, step_index=0, channel="whatsapp",
            status="sent", template_slug="welcome_message",
            idempotency_key=f"flowmem_{member.id}_step_0_whatsapp",
        ))
        db.commit()

        rows = db.query(FlowStepRun).filter(FlowStepRun.membership_id == member.id).all()
        assert len(rows) == 2
    finally:
        db.close()


# ─── Sample Dispatch seed + endpoints ────────────────────────────────


def test_sample_dispatch_flow_seeded(client: TestClient, auth_headers: dict[str, str]) -> None:
    """The boot-time seeder inserts the sample_dispatch flow with the
    tag trigger config and 3 steps."""
    from services.database import get_db
    from services.models import Flow

    db = get_db()
    try:
        flow = db.query(Flow).filter(Flow.slug == "sample_dispatch").first()
        assert flow is not None
        assert flow.trigger_type == "tag"
        assert (flow.trigger_config or {}).get("tag") == "samples_requested"
        steps = flow.steps or []
        assert len(steps) == 3
        # Step 0 is multi-channel + immediate
        assert steps[0]["channel"] == "both"
        # Step 1 is event-gated
        assert steps[1].get("trigger_event", {}).get("value") == "samples_shipped"
    finally:
        db.close()


def test_create_membership_endpoint(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    from services.database import get_db
    from services.models import Flow

    db = get_db()
    try:
        flow = (
            db.query(Flow).filter(Flow.slug == "sample_dispatch").first()
        )
        assert flow is not None
        flow_id = flow.id
    finally:
        db.close()

    cid = _seed_contact("manual_assign")
    res = client.post(
        f"/api/v2/flows/{flow_id}/memberships",
        json={"contact_id": cid, "actor": "test_user"},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["contact_id"] == cid
    assert body["flow_slug"] == "sample_dispatch"
    assert body["status"] == "active"

    # Second call should 409.
    res2 = client.post(
        f"/api/v2/flows/{flow_id}/memberships",
        json={"contact_id": cid},
        headers=auth_headers,
    )
    assert res2.status_code == 409


def test_stop_membership_endpoint(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    from services.database import get_db
    from services.models import Flow

    db = get_db()
    try:
        flow_id = (
            db.query(Flow).filter(Flow.slug == "sample_dispatch").first().id
        )
    finally:
        db.close()

    cid = _seed_contact("stop_member")
    create_res = client.post(
        f"/api/v2/flows/{flow_id}/memberships",
        json={"contact_id": cid},
        headers=auth_headers,
    )
    member_id = create_res.json()["id"]

    res = client.post(
        f"/api/v2/flow-memberships/{member_id}/stop",
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "stopped"


def test_contact_flow_memberships_endpoint(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    from services.database import get_db
    from services.models import Flow

    db = get_db()
    try:
        flow_id = (
            db.query(Flow).filter(Flow.slug == "sample_dispatch").first().id
        )
    finally:
        db.close()

    cid = _seed_contact("drawer_data")
    client.post(
        f"/api/v2/flows/{flow_id}/memberships",
        json={"contact_id": cid},
        headers=auth_headers,
    )

    res = client.get(
        f"/api/v2/contacts/{cid}/flow-memberships",
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] >= 1
    assert any(m["flow_slug"] == "sample_dispatch" for m in body["memberships"])


def test_mark_sample_shipped_endpoint(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The Mark Sample Shipped endpoint should add the tag, write
    tracking onto the membership's metadata_json, and resume the
    waiting step."""
    from services.database import get_db
    from services.models import Contact, Flow, FlowMembership

    db = get_db()
    try:
        flow_id = (
            db.query(Flow).filter(Flow.slug == "sample_dispatch").first().id
        )
    finally:
        db.close()

    cid = _seed_contact("mark_shipped")

    # Manually park a membership at waiting_event/step 1 to simulate the
    # state after step 0 has fired and the operator is about to ship.
    db = get_db()
    try:
        member = FlowMembership(
            flow_id=flow_id,
            contact_id=cid,
            status="waiting_event",
            current_step_index=1,
            next_fire_at=None,
            trigger_source="tag",
            trigger_payload={"tag": "samples_requested"},
        )
        db.add(member)
        db.commit()
        member_id = member.id
    finally:
        db.close()

    res = client.post(
        f"/api/v2/contacts/{cid}/mark-sample-shipped",
        json={"tracking_id": "TEST-TRK-123", "courier_name": "BlueDart"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tag_added"] is True
    assert member_id in body["memberships_updated"]

    db = get_db()
    try:
        m = db.query(FlowMembership).filter(FlowMembership.id == member_id).one()
        # Resumed back to active by the tag-trigger evaluator (since
        # step 1's trigger_event is tag=samples_shipped).
        assert m.status == "active"
        assert m.next_fire_at is not None
        meta = m.metadata_json or {}
        assert meta.get("tracking_id") == "TEST-TRK-123"
        assert meta.get("courier_name") == "BlueDart"

        c = db.query(Contact).filter(Contact.id == cid).one()
        assert "samples_shipped" in (c.tags or [])
    finally:
        db.close()


# ─── review findings: regression tests ──────────────────────────────


def test_assign_flow_savepoint_does_not_poison_outer_transaction() -> None:
    """Review finding #1.

    If a concurrent trigger races and the partial unique index rejects
    the membership insert, the SAVEPOINT must roll back ONLY that
    insert. The caller's pending writes (e.g. the lifecycle change in
    `set_contact_lifecycle`) must survive — otherwise the lifecycle
    update is silently lost while the request still returns 200.

    We simulate the race by:
      1. Inserting a live membership directly so the unique index is
         armed.
      2. Monkey-patching `_has_live_membership` to return False (the
         pre-check is the cheap defence; the index is the structural
         one).
      3. Making a pending Contact mutation in the session.
      4. Calling `assign_flow` — it must hit IntegrityError, return
         None, and the pending Contact mutation must still be visible
         after `db.commit()`.
    """
    from api_v2.services import flows_engine_v2 as engine
    from services.database import get_db
    from services.models import Contact, FlowMembership

    flow_id = _seed_tag_flow("test_savepoint")
    cid = _seed_contact("savepoint")

    db = get_db()
    try:
        db.add(
            FlowMembership(
                flow_id=flow_id,
                contact_id=cid,
                status="active",
                current_step_index=0,
                trigger_source="manual",
            )
        )
        db.commit()

        # Pending mutation that must NOT be lost when assign_flow's
        # IntegrityError fires.
        contact = db.query(Contact).filter(Contact.id == cid).one()
        contact.lifecycle = "interested"
        contact.notes = "lifecycle change must survive trigger race"

        # Force assign_flow past the pre-insert SELECT so the partial
        # unique index is the thing that rejects the row.
        with patch.object(engine, "_has_live_membership", return_value=False):
            result = engine.assign_flow(
                db,
                flow_id=flow_id,
                contact_id=cid,
                trigger_source="lifecycle",
            )
        assert result is None, "duplicate insert should swallow"

        # The savepoint rolled back ONLY the membership insert; the
        # contact mutation should commit cleanly.
        db.commit()

        fresh = get_db()
        try:
            c2 = fresh.query(Contact).filter(Contact.id == cid).one()
            assert c2.lifecycle == "interested"
            assert "must survive" in (c2.notes or "")
        finally:
            fresh.close()
    finally:
        db.close()


def test_send_exception_marks_placeholder_failed_no_false_advance() -> None:
    """Review finding #2.

    If the sender raises mid-flight, the engine must mark the
    `flow_step_runs` placeholder failed so the next tick sees a
    terminal state — not silently treat the stranded 'sending' row as
    'sent' and advance the membership.
    """
    from api_v2.services.flows_engine_v2 import tick_flows
    from services.database import get_db
    from services.models import EmailTemplate, FlowMembership, FlowStepRun

    flow_id = _seed_tag_flow("test_send_exception")
    cid = _seed_contact("send_exception")

    db = get_db()
    try:
        if not db.query(EmailTemplate).filter(EmailTemplate.slug == "welcome").first():
            db.add(EmailTemplate(slug="welcome", name="Welcome", subject_template="Hi"))
            db.commit()

        member = FlowMembership(
            flow_id=flow_id,
            contact_id=cid,
            status="active",
            current_step_index=0,
            next_fire_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            trigger_source="manual",
        )
        db.add(member)
        db.commit()
        member_id = member.id
    finally:
        db.close()

    fake_sender = MagicMock()
    fake_sender.is_configured.return_value = True
    fake_sender.send_email.side_effect = RuntimeError("simulated SMTP outage")

    with (
        patch("services.email_sender.EmailSender", return_value=fake_sender),
        patch(
            "services.email_sender.render_template_by_slug",
            return_value="<html>ok</html>",
        ),
        patch(
            "services.email_sender.render_template_string",
            return_value="rendered subject",
        ),
        patch("api_v2.services.flows_engine_v2.time.sleep"),
    ):
        tick_flows()

    db = get_db()
    try:
        m = db.query(FlowMembership).filter(FlowMembership.id == member_id).one()
        # The membership did NOT advance — step 0 failed terminally.
        assert m.current_step_index == 0
        # The placeholder row exists with status='failed', not 'sending'.
        runs = (
            db.query(FlowStepRun)
            .filter(FlowStepRun.membership_id == member_id)
            .all()
        )
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert "send_exception" in (runs[0].error or "")
        # consecutive_failures incremented; membership re-armed for retry.
        assert (m.consecutive_failures or 0) == 1
    finally:
        db.close()


# ─── Phase 7.8: pause / resume + GET /flows/{id} ────────────────────


def test_pause_membership_clears_next_fire_at(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """POST /flow-memberships/{id}/pause sets status='paused' and
    clears next_fire_at. tick_flows must NOT claim paused rows."""
    from api_v2.services.flows_engine_v2 import tick_flows
    from services.database import get_db
    from services.models import FlowMembership

    flow_id = _seed_tag_flow("test_pause")
    cid = _seed_contact("pause_target")

    db = get_db()
    try:
        m = FlowMembership(
            flow_id=flow_id,
            contact_id=cid,
            status="active",
            current_step_index=0,
            next_fire_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            trigger_source="manual",
        )
        db.add(m)
        db.commit()
        member_id = m.id
    finally:
        db.close()

    res = client.post(
        f"/api/v2/flow-memberships/{member_id}/pause",
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "paused"
    assert body["next_fire_at"] is None

    # Confirm tick_flows skips paused rows.
    result = tick_flows()
    db = get_db()
    try:
        m2 = db.query(FlowMembership).filter(FlowMembership.id == member_id).one()
        assert m2.status == "paused", "tick must not claim paused rows"
        assert m2.current_step_index == 0
    finally:
        db.close()


def test_resume_membership_re_arms_next_fire_at(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """POST /flow-memberships/{id}/resume from paused → active with
    next_fire_at=now. The next tick claims it."""
    from services.database import get_db
    from services.models import FlowMembership

    flow_id = _seed_tag_flow("test_resume")
    cid = _seed_contact("resume_target")

    db = get_db()
    try:
        m = FlowMembership(
            flow_id=flow_id,
            contact_id=cid,
            status="paused",
            current_step_index=0,
            next_fire_at=None,
            trigger_source="manual",
            error="some prior error",
        )
        db.add(m)
        db.commit()
        member_id = m.id
    finally:
        db.close()

    res = client.post(
        f"/api/v2/flow-memberships/{member_id}/resume",
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "active"
    assert body["next_fire_at"] is not None
    assert body["error"] == ""  # cleared on resume


def test_pause_rejects_terminal_status(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """409 when transitioning out of a terminal status."""
    from services.database import get_db
    from services.models import FlowMembership

    flow_id = _seed_tag_flow("test_pause_terminal")
    cid = _seed_contact("pause_terminal")

    db = get_db()
    try:
        m = FlowMembership(
            flow_id=flow_id,
            contact_id=cid,
            status="completed",
            current_step_index=2,
            next_fire_at=None,
            trigger_source="manual",
        )
        db.add(m)
        db.commit()
        member_id = m.id
    finally:
        db.close()

    res = client.post(
        f"/api/v2/flow-memberships/{member_id}/pause",
        headers=auth_headers,
    )
    assert res.status_code == 409


def test_resume_rejects_non_paused(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """409 when resuming a membership that isn't paused."""
    from services.database import get_db
    from services.models import FlowMembership

    flow_id = _seed_tag_flow("test_resume_non_paused")
    cid = _seed_contact("resume_non_paused")

    db = get_db()
    try:
        m = FlowMembership(
            flow_id=flow_id,
            contact_id=cid,
            status="active",
            current_step_index=0,
            next_fire_at=datetime.now(timezone.utc),
            trigger_source="manual",
        )
        db.add(m)
        db.commit()
        member_id = m.id
    finally:
        db.close()

    res = client.post(
        f"/api/v2/flow-memberships/{member_id}/resume",
        headers=auth_headers,
    )
    assert res.status_code == 409


def test_get_flow_detail_endpoint(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """GET /api/v2/flows/{id} returns the full steps array + per-status counts."""
    from services.database import get_db
    from services.models import Flow, FlowMembership

    db = get_db()
    try:
        flow = db.query(Flow).filter(Flow.slug == "sample_dispatch").first()
        assert flow is not None
        flow_id = flow.id
    finally:
        db.close()

    cid_active = _seed_contact("flow_detail_active")
    cid_completed = _seed_contact("flow_detail_completed")

    db = get_db()
    try:
        db.add(
            FlowMembership(
                flow_id=flow_id, contact_id=cid_active,
                status="active", current_step_index=0,
                next_fire_at=datetime.now(timezone.utc),
                trigger_source="manual",
            )
        )
        db.add(
            FlowMembership(
                flow_id=flow_id, contact_id=cid_completed,
                status="completed", current_step_index=3,
                next_fire_at=None,
                trigger_source="manual",
            )
        )
        db.commit()
    finally:
        db.close()

    res = client.get(f"/api/v2/flows/{flow_id}", headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["slug"] == "sample_dispatch"
    assert body["trigger_type"] == "tag"
    assert body["channel"] == "multi"
    assert isinstance(body["steps"], list)
    assert len(body["steps"]) == 3
    assert isinstance(body["counts"], dict)
    # active_count rolls up active+waiting_event+paused
    assert body["counts"].get("active", 0) >= 1
    assert body["counts"].get("completed", 0) >= 1


def test_get_flow_detail_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.get("/api/v2/flows/9999999", headers=auth_headers)
    assert res.status_code == 404


def test_contact_flow_memberships_includes_current_step(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The drawer needs the current step JSON inline so it knows
    whether to render the Mark Sample Shipped button."""
    from services.database import get_db
    from services.models import Flow, FlowMembership

    db = get_db()
    try:
        flow_id = (
            db.query(Flow).filter(Flow.slug == "sample_dispatch").first().id
        )
    finally:
        db.close()

    cid = _seed_contact("drawer_current_step")

    db = get_db()
    try:
        db.add(
            FlowMembership(
                flow_id=flow_id, contact_id=cid,
                status="waiting_event", current_step_index=1,
                next_fire_at=None,
                trigger_source="tag",
            )
        )
        db.commit()
    finally:
        db.close()

    res = client.get(
        f"/api/v2/contacts/{cid}/flow-memberships",
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] >= 1
    sample = next((m for m in body["memberships"] if m["flow_slug"] == "sample_dispatch"), None)
    assert sample is not None
    assert sample["flow_trigger_type"] == "tag"
    assert sample["current_step"] is not None
    # Step 1 of Sample Dispatch is event-gated on samples_shipped.
    assert sample["current_step"]["trigger_event"]["value"] == "samples_shipped"


def test_assign_flow_partial_unique_blocks_duplicate() -> None:
    """The pre-insert SELECT in assign_flow returns None for an active
    duplicate; the partial unique index would also block at the DB
    layer if the SELECT race lost."""
    from api_v2.services.flows_engine_v2 import assign_flow
    from services.database import get_db
    from services.models import FlowMembership

    flow_id = _seed_tag_flow("test_partial_uniq")
    cid = _seed_contact("partial_uniq")

    db = get_db()
    try:
        m1 = assign_flow(
            db, flow_id=flow_id, contact_id=cid,
            trigger_source="manual", commit=True,
        )
        assert m1 is not None
        m2 = assign_flow(
            db, flow_id=flow_id, contact_id=cid,
            trigger_source="manual", commit=True,
        )
        assert m2 is None  # already enrolled
        n = (
            db.query(FlowMembership)
            .filter(
                FlowMembership.flow_id == flow_id,
                FlowMembership.contact_id == cid,
            )
            .count()
        )
        assert n == 1
    finally:
        db.close()
