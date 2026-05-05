"""Tests for the email_sent interaction logging added to v1's send loop.

The actual send loop is a Gradio event handler in
hf_dashboard/pages/email_broadcast.py — too coupled to invoke directly.
These tests instead exercise the contract that loop relies on:

  log_interaction(db, contact_id, kind="email_sent", summary, payload,
                  actor="campaign", commit=False)

must produce exactly one ContactInteraction row with the expected fields,
must not commit (caller does), and must tolerate missing contact_id without
raising.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HF_DASHBOARD = _REPO_ROOT / "hf_dashboard"
if _HF_DASHBOARD.exists() and str(_HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_HF_DASHBOARD))

# Match conftest.py — point v1 services at the test SQLite DB.
_TEST_DB = _HF_DASHBOARD / "data" / "test_api_v2.db"
_TEST_DB.parent.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = ""
os.environ["SQLITE_PATH"] = str(_TEST_DB)
os.environ.setdefault("APP_PASSWORD", "test_secret")


@pytest.fixture()
def db_session():
    """Yield a fresh DB session against the test DB. Rolls back after."""
    from services.database import ensure_db_ready, get_db

    ensure_db_ready()
    db = get_db()
    yield db
    db.rollback()
    db.close()


@pytest.fixture()
def contact(db_session):
    """Create a test contact and yield it. Cleans up after."""
    from services.models import Contact

    c = Contact(
        id="test_email_sent",
        email="ci-test@example.com",
        first_name="CI",
        last_name="Test",
    )
    db_session.add(c)
    db_session.commit()
    yield c

    # Teardown — remove the contact and any interactions tied to it.
    from services.models import ContactInteraction

    db_session.query(ContactInteraction).filter(
        ContactInteraction.contact_id == c.id
    ).delete()
    db_session.query(Contact).filter(Contact.id == c.id).delete()
    db_session.commit()


def test_email_sent_interaction_writes_one_row(db_session, contact):
    """Successful broadcast send → one email_sent row with full payload."""
    from services.interactions import log_interaction
    from services.models import ContactInteraction

    log_interaction(
        db_session,
        contact_id=contact.id,
        kind="email_sent",
        summary="B2B Introduction: Premium Himalayan Fibers for Acme Corp",
        payload={
            "campaign_id": 42,
            "template_slug": "b2b_introduction",
            "subject": "Premium Himalayan Fibers for Acme Corp",
        },
        actor="campaign",
        commit=False,
    )
    db_session.commit()

    rows = (
        db_session.query(ContactInteraction)
        .filter(ContactInteraction.contact_id == contact.id)
        .filter(ContactInteraction.kind == "email_sent")
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor == "campaign"
    assert row.summary.startswith("B2B Introduction:")
    assert row.payload["campaign_id"] == 42
    assert row.payload["template_slug"] == "b2b_introduction"


def test_log_interaction_with_commit_false_does_not_commit(db_session, contact):
    """commit=False must defer the commit — caller is responsible for it."""
    from services.interactions import log_interaction
    from services.models import ContactInteraction

    log_interaction(
        db_session,
        contact_id=contact.id,
        kind="email_sent",
        summary="deferred",
        actor="campaign",
        commit=False,
    )

    # Row exists in this session but has not been flushed to DB yet — but a
    # rollback would erase it, proving commit didn't happen.
    db_session.rollback()

    rows = (
        db_session.query(ContactInteraction)
        .filter(ContactInteraction.contact_id == contact.id)
        .all()
    )
    assert rows == []


def test_log_interaction_skips_empty_contact_id(db_session):
    """Failed sends shouldn't crash the loop on a missing contact_id."""
    from services.interactions import log_interaction
    from services.models import ContactInteraction

    result = log_interaction(
        db_session,
        contact_id="",
        kind="email_sent",
        summary="ignored",
        actor="campaign",
        commit=False,
    )
    assert result is None

    rows = (
        db_session.query(ContactInteraction)
        .filter(ContactInteraction.kind == "email_sent")
        .filter(ContactInteraction.summary == "ignored")
        .all()
    )
    assert rows == []
