"""SQLite database engine + CSV seeder.

On first run, creates all tables and seeds from CSV files.
Uses WAL journal mode for concurrent read safety.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from services.config import get_settings
from services.models import (
    Base, Contact, Segment, Campaign, EmailSend, EmailAttachment, Flow, FlowRun,
    WAChat, WAMessage, WATemplate, EmailTemplate, Broadcast,
    ContactInteraction, ContactNote,
)

log = logging.getLogger(__name__)

_engine = None
_SessionLocal = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _preflight_postgres(db_url: str) -> None:
    """Raw TCP reachability + DNS check for the Postgres host.

    Runs BEFORE SQLAlchemy opens a connection so the failure message is clear
    and fast (10s instead of psycopg2's default ~60s). Logs a loud, actionable
    diagnostic if the host is unreachable, then raises with the same message.
    """
    import socket
    from urllib.parse import urlparse

    p = urlparse(db_url)
    host = p.hostname or "?"
    port = p.port or 5432
    user = p.username or "?"
    log.info("DB preflight: host=%s port=%s user=%s", host, port, user)

    # 1. DNS resolution
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        resolved = sorted({i[4][0] for i in infos})
        log.info("DB preflight: DNS %s -> %s", host, ", ".join(resolved))
    except socket.gaierror as e:
        msg = (
            f"DB UNREACHABLE: DNS lookup failed for host={host}. "
            f"Check DATABASE_URL spelling. Error: {e}"
        )
        log.error("\n" + "=" * 72 + "\n" + msg + "\n" + "=" * 72)
        raise RuntimeError(msg) from e

    # 2. TCP connect on each resolved address, 10s timeout each
    last_err = None
    for ip in resolved:
        try:
            with socket.create_connection((ip, port), timeout=10) as s:
                log.info("DB preflight: TCP %s:%s OK", ip, port)
                return  # reachable
        except (socket.timeout, OSError) as e:
            last_err = e
            log.warning("DB preflight: TCP %s:%s failed (%s)", ip, port, e)

    # All IPs failed — emit a loud diagnostic
    hint = ""
    if port == 5432:
        hint = (
            "\nHINT: You are using port 5432 (session/direct). Supabase free-tier "
            "projects are blocked from direct IPv4 — use the TRANSACTION POOLER on "
            "port 6543 instead. In Supabase → Project Settings → Database → "
            "Connection string → 'Transaction pooler', copy the URI and update the "
            "DATABASE_URL secret in HF Space → Settings → Variables & Secrets."
        )
    elif port == 6543:
        hint = (
            "\nHINT: Port 6543 is the transaction pooler. The host is resolving but "
            "TCP is blocked. Check Supabase → Database → Network Restrictions "
            "(set to 'Allow all' if restricted), and verify no IP allowlist is "
            "excluding HF Spaces egress."
        )
    msg = (
        f"DB UNREACHABLE: TCP connect to {host}:{port} timed out on all "
        f"resolved IPs ({', '.join(resolved)}). Last error: {last_err}.{hint}"
    )
    log.error("\n" + "=" * 72 + "\n" + msg + "\n" + "=" * 72)
    raise RuntimeError(msg)


def get_engine():
    """Lazy-create the SQLAlchemy engine.

    Uses Postgres (Supabase) if DATABASE_URL is set — persistent across HF
    Spaces container restarts. Falls back to local SQLite for dev when
    DATABASE_URL is not set.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.database_url:
            log.info("DB engine: Postgres (%s)", _mask_db_url(settings.database_url))
            _preflight_postgres(settings.database_url)
            _engine = create_engine(
                settings.database_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
                echo=False,
                connect_args={"connect_timeout": 10},
            )
            # Plan D Phase 0: attach the egress tracker so we can rank
            # actual DB readers by rows returned. No-op for SQLite.
            try:
                from services.egress_tracker import install_egress_tracker
                install_egress_tracker(_engine)
            except Exception:
                log.exception("egress_tracker install failed")
        else:
            db_path = Path(settings.sqlite_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False},
                echo=False,
            )
            with _engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA busy_timeout=5000"))
                conn.commit()
            log.info("DB engine: SQLite (%s)", db_path)
    return _engine


def _mask_db_url(url: str) -> str:
    """Return a safe-to-log version of the DB URL with the password hidden."""
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        if p.password:
            netloc = p.netloc.replace(f":{p.password}", ":***")
            p = p._replace(netloc=netloc)
        return urlunparse(p)
    except Exception:
        return "<db>"


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal


def get_db() -> Session:
    """Get a database session."""
    factory = get_session_factory()
    return factory()


def init_db():
    """Create all tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    log.info("Database tables created")


def is_db_seeded() -> bool:
    """Check if contacts table has data."""
    db = get_db()
    try:
        count = db.query(Contact).count()
        return count > 0
    finally:
        db.close()


def seed_from_csv():
    """Seed the database from CSV files in data/ directory."""
    db = get_db()
    try:
        _seed_contacts(db)
        _seed_segments(db)
        _seed_default_templates(db)
        _seed_default_flows(db)
        db.commit()
        log.info("Database seeded successfully")
    except Exception:
        db.rollback()
        log.exception("Failed to seed database")
        raise
    finally:
        db.close()


def _compute_lifecycle(customer_type: str, consent_status: str, total_emails_sent: int) -> str:
    """Auto-assign lifecycle based on contact data."""
    if customer_type == "existing_client":
        return "customer"
    if consent_status == "opted_out":
        return "churned"
    if consent_status == "opted_in":
        return "interested"
    if total_emails_sent > 0:
        return "contacted"
    return "new_lead"


def _seed_contacts(db: Session):
    """Load contacts from contacts.csv."""
    csv_path = DATA_DIR / "contacts.csv"
    if not csv_path.exists():
        log.warning("contacts.csv not found at %s", csv_path)
        return

    df = pd.read_csv(csv_path, dtype=str).fillna("")
    count = 0
    for _, row in df.iterrows():
        phone = str(row.get("phone", "")).strip()

        # Prefer wa_id from CSV if present; otherwise derive from phone.
        wa_id = str(row.get("wa_id", "")).strip() or None
        if not wa_id and phone:
            if len(phone) == 10 and phone.isdigit():
                wa_id = f"91{phone}"
            elif len(phone) > 10:
                wa_id = phone.lstrip("+")

        tags_raw = str(row.get("tags", "")).strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        email_val = row.get("email", "") or None
        # Skip duplicates (email or wa_id)
        if email_val and db.query(Contact).filter(Contact.email == email_val).first():
            continue
        if wa_id and db.query(Contact).filter(Contact.wa_id == wa_id).first():
            wa_id = None  # Clear duplicate wa_id, keep contact

        # Lifecycle: use CSV value when present, fall back to derivation.
        lifecycle = str(row.get("lifecycle", "")).strip() or _compute_lifecycle(
            row.get("customer_type", ""),
            row.get("consent_status", "pending"),
            int(row.get("total_emails_sent", 0) or 0),
        )

        contact = Contact(
            id=row.get("id", str(uuid.uuid4())[:8]),
            email=email_val,
            first_name=row.get("first_name", ""),
            last_name=row.get("last_name", ""),
            company=row.get("company", ""),
            phone=phone,
            website=row.get("website", ""),
            address=row.get("address", ""),
            city=row.get("city", ""),
            state=row.get("state", ""),
            country=row.get("country", ""),
            postal_code=row.get("postal_code", ""),
            customer_type=row.get("customer_type", ""),
            customer_subtype=row.get("customer_subtype", ""),
            geography=row.get("geography", ""),
            engagement_level=row.get("engagement_level", "new"),
            tags=tags,
            consent_status=row.get("consent_status", "pending"),
            consent_source=row.get("consent_source", ""),
            lifecycle=lifecycle,
            total_emails_sent=int(row.get("total_emails_sent", 0) or 0),
            total_emails_opened=int(row.get("total_emails_opened", 0) or 0),
            total_emails_clicked=int(row.get("total_emails_clicked", 0) or 0),
            is_dispatched=row.get("is_dispatched", "").lower() == "true",
            is_contacted=row.get("is_contacted", "").lower() == "true",
            response_notes=row.get("response_notes", ""),
            priority=row.get("priority", ""),
            source=row.get("source", ""),
            notes=row.get("notes", ""),
            wa_id=wa_id,
            wa_consent_status=row.get("wa_consent_status", "unknown") or "unknown",
            wa_profile_name=row.get("wa_profile_name", ""),
        )
        db.add(contact)
        count += 1

    db.flush()
    log.info("Seeded %d contacts", count)


def _seed_segments(db: Session):
    """Load segments from segments.csv."""
    csv_path = DATA_DIR / "segments.csv"
    if not csv_path.exists():
        log.warning("segments.csv not found at %s", csv_path)
        return

    df = pd.read_csv(csv_path, dtype=str).fillna("")
    count = 0
    for _, row in df.iterrows():
        rules_str = row.get("rules_json", "{}")
        try:
            rules = json.loads(rules_str) if rules_str else {}
        except json.JSONDecodeError:
            rules = {}

        segment = Segment(
            id=row.get("id", str(uuid.uuid4())[:8]),
            name=row.get("name", ""),
            description=row.get("description", ""),
            rules=rules,
            is_active=row.get("is_active", "True").lower() == "true",
        )
        db.add(segment)
        count += 1

    db.flush()
    log.info("Seeded %d segments", count)


def _seed_default_templates(db: Session):
    """Register email templates from templates/ directory."""
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    if not templates_dir.exists():
        return

    template_defs = [
        ("B2B Introduction - Carpet Exporters", "b2b_introduction", "campaigns/b2b_introduction_carpet_exporters.html", "Premium Himalayan Fibers for {{company_name}}"),
        ("Sustainability Compliance", "sustainability", "campaigns/sustainability_compliance_campaign.html", "Meet EU & US Sustainability Standards"),
        ("Tariff Advantage", "tariff_advantage", "campaigns/tariff_advantage_campaign.html", "Beat Import Tariffs with Domestic Himalayan Fibers"),
        ("Welcome Email Final", "welcome_final", "campaigns/welcome_email_final.html", "Welcome to Himalayan Fibers, {{name}}"),
        ("Welcome Email Production", "welcome_production", "campaigns/welcome_email_production.html", "Welcome to Himalayan Fibers"),
        # NOTE: legacy `order_confirmation` removed — replaced by the new
        # seed loader that reads from config/email/templates_seed/ and
        # compiles Jinja2 templates with the locked shell partials.
        ("Welcome (Transactional)", "welcome_transactional", "transactional/welcome.html", "Welcome to Himalayan Fibers, {{first_name}}"),
    ]

    for name, slug, path, subject in template_defs:
        full_path = templates_dir / path
        html = ""
        if full_path.exists():
            html = full_path.read_text(encoding="utf-8")

        tpl = EmailTemplate(
            name=name,
            slug=slug,
            subject_template=subject,
            html_content=html,
            email_type="campaign" if "campaigns" in path else "transactional",
            category="campaign" if "campaigns" in path else "transactional",
        )
        db.add(tpl)

    db.flush()
    log.info("Seeded %d email templates", len(template_defs))


def _seed_default_flows(db: Session):
    """Create pre-defined automation flows."""
    flows = [
        Flow(
            name="B2B Introduction Flow",
            description="3-step email sequence for new B2B carpet exporter leads",
            channel="email",
            steps=[
                {"day": 0, "template_slug": "b2b_introduction", "subject": "Premium Himalayan Fibers for {{company_name}}"},
                {"day": 3, "template_slug": "sustainability", "subject": "Meet EU & US Sustainability Standards"},
                {"day": 7, "template_slug": "tariff_advantage", "subject": "Beat Import Tariffs with Domestic Himalayan Fibers"},
            ],
        ),
        Flow(
            name="Welcome & Nurture Flow",
            description="2-step welcome email sequence for new contacts",
            channel="email",
            steps=[
                {"day": 0, "template_slug": "welcome_production", "subject": "Welcome to Himalayan Fibers"},
                {"day": 5, "template_slug": "welcome_final", "subject": "Discover Our Product Range"},
            ],
        ),
        Flow(
            name="WhatsApp Welcome Flow",
            description="2-step WhatsApp template sequence for new leads",
            channel="whatsapp",
            steps=[
                {"day": 0, "wa_template": "welcome_message", "variables": ["{{first_name}}"]},
                {"day": 3, "wa_template": "snow_white", "variables": []},
            ],
        ),
    ]

    for flow in flows:
        db.add(flow)

    db.flush()
    log.info("Seeded %d flows", len(flows))


def ensure_db_ready():
    """Initialize DB and seed if needed. Called on app startup."""
    init_db()
    if not is_db_seeded():
        log.info("Database empty — seeding from CSV...")
        seed_from_csv()
    else:
        log.info("Database already seeded (%d contacts)", get_db().query(Contact).count())

    # Seed the Jinja2-based email templates (idempotent — skips slugs
    # that already exist so founder edits are preserved). Runs on every
    # boot so newly added templates_seed/*.meta.yml files are picked up.
    try:
        from services.template_seed import seed_email_templates
        db = get_db()
        try:
            summary = seed_email_templates(db, force=False)
            log.info("Email template seed: %s", summary)
        finally:
            db.close()
    except Exception:
        log.exception("Email template seed failed (non-fatal)")
