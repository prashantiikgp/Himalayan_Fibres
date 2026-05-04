"""
Wipe contact-related tables on the production Supabase Postgres and
reseed contacts + segments from `hf_dashboard/data/{contacts,segments}.csv`.

User confirmed (2026-05-04) that no meaningful email-send / WA history
needs preserving, so this script does a destructive reset.

Tables wiped (TRUNCATE ... RESTART IDENTITY CASCADE):
  - contacts                 (target — also cascades to FK children)
  - segments                 (rebuilt from segments.csv)
  - email_sends              (logical FK on contact_id)
  - wa_chats / wa_messages   (logical FK on contact_id)
  - email_attachments / contact_interactions / contact_notes
    (FK with no explicit cascade — TRUNCATE ... CASCADE handles them)

Tables left alone:
  - email_templates / campaigns / flows / flow_runs / broadcasts
  - wa_templates / product_media

Run:
    python scripts/data_v3/wipe_and_reseed_supabase.py            # prompts y/N
    python scripts/data_v3/wipe_and_reseed_supabase.py --yes      # skip prompt
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hf_dashboard"))

# Load .env so DATABASE_URL is available before importing services.database.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(REPO / ".env")
except ImportError:
    pass

from sqlalchemy import text  # noqa: E402

import services.database as db_mod  # noqa: E402
from services.models import Contact, Segment  # noqa: E402

WIPE_TABLES = [
    "email_attachments",
    "contact_interactions",
    "contact_notes",
    "email_sends",
    "wa_messages",
    "wa_chats",
    "segments",
    "contacts",
]


def main() -> None:
    yes = "--yes" in sys.argv or "-y" in sys.argv

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        sys.exit("DATABASE_URL not set. Add it to .env or export it.")

    if "supabase" not in db_url and "postgres" not in db_url:
        sys.exit(f"Refusing to wipe — DATABASE_URL does not look like Postgres: {db_url[:40]}...")

    redacted = db_url.split("@")[-1] if "@" in db_url else db_url
    print(f"Target DB: ...@{redacted}")

    engine = db_mod.get_engine()

    # Pre-wipe row counts.
    with engine.connect() as conn:
        existing = {}
        for tbl in WIPE_TABLES:
            try:
                r = conn.execute(text(f"SELECT count(*) FROM {tbl}")).scalar()
                existing[tbl] = r
            except Exception as e:
                existing[tbl] = f"<error: {e.__class__.__name__}>"

    print("\nCurrent row counts:")
    for tbl, n in existing.items():
        print(f"  {tbl:<24s} {n}")

    if not yes:
        ans = input("\nProceed with TRUNCATE + reseed? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            sys.exit("Aborted.")

    # TRUNCATE in one statement so CASCADE picks up everything cleanly.
    tables_sql = ", ".join(WIPE_TABLES)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {tables_sql} RESTART IDENTITY CASCADE"))
    print(f"\nTruncated: {tables_sql}")

    # Reseed contacts + segments via the existing seeders.
    session = db_mod.get_db()
    try:
        db_mod._seed_contacts(session)
        db_mod._seed_segments(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    # Post-seed counts.
    s = db_mod.get_db()
    try:
        n_contacts = s.query(Contact).count()
        n_segments = s.query(Segment).count()
    finally:
        s.close()

    print(f"\nReseeded: contacts={n_contacts}, segments={n_segments}")
    print("Done. The HF dashboard will now show v3 data on next page load.")


if __name__ == "__main__":
    main()
