"""
Combine the 4 Data_v3 CSVs into a single contacts.csv that matches the
dashboard's seed-file schema (`hf_dashboard/services/database.py::_seed_contacts`).

Writes to:
  - data/contacts.csv
  - hf_dashboard/data/contacts.csv

Run:
    python scripts/data_v3/build_contacts_csv.py
"""
from __future__ import annotations

import csv
import datetime as dt
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = [
    REPO / "Data" / "Data_v3" / "01_existing_clients.csv",
    REPO / "Data" / "Data_v3" / "02_lapsed_clients.csv",
    REPO / "Data" / "Data_v3" / "03_carpet_exporters_india.csv",
    REPO / "Data" / "Data_v3" / "04_yarn_stores_international.csv",
]
DESTS = [
    REPO / "data" / "contacts.csv",
    REPO / "hf_dashboard" / "data" / "contacts.csv",
]

# Mirrors hf_dashboard/services/models.py::Contact (all 38 columns).
DEST_FIELDS = [
    "id", "email", "first_name", "last_name", "company", "phone",
    "website", "address", "city", "state", "country", "postal_code",
    "customer_type", "customer_subtype", "geography", "engagement_level",
    "tags", "consent_status", "consent_source", "lifecycle",
    "total_emails_sent", "total_emails_opened", "total_emails_clicked",
    "last_email_sent_at", "last_email_opened_at",
    "is_dispatched", "is_contacted",
    "response_notes", "priority", "source", "notes",
    "wa_id", "wa_consent_status", "wa_profile_name",
    "last_wa_inbound_at", "last_wa_outbound_at",
    "created_at", "updated_at",
]


def _compute_lifecycle(customer_type: str, consent_status: str, total_emails_sent: int) -> str:
    if customer_type == "existing_client":
        return "customer"
    if consent_status == "opted_out":
        return "churned"
    if consent_status == "opted_in":
        return "interested"
    if total_emails_sent > 0:
        return "contacted"
    return "new_lead"


def _phone_to_wa_id(phone: str) -> str:
    p = phone.strip()
    if not p:
        return ""
    if p.startswith("+"):
        return p.lstrip("+")
    if len(p) == 10 and p.isdigit():
        return f"91{p}"
    return p


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    out_rows = []
    seen_emails: set[str] = set()
    skipped_dupe = 0

    for src in SOURCES:
        with open(src) as f:
            for r in csv.DictReader(f):
                email = r["email"].strip().lower()
                if not email:
                    continue
                if email in seen_emails:
                    skipped_dupe += 1
                    continue
                seen_emails.add(email)

                phone = r["phone"].strip()
                customer_type = r["customer_type"].strip()
                consent_status = r["consent_status"].strip()

                out_rows.append({
                    "id": uuid.uuid4().hex[:8],
                    "email": r["email"].strip(),
                    "first_name": r["first_name"].strip(),
                    "last_name": r["last_name"].strip(),
                    "company": r["company"].strip(),
                    "phone": phone,
                    "website": "",
                    "address": "",
                    "city": "",
                    "state": "",
                    "country": r["country"].strip(),
                    "postal_code": "",
                    "customer_type": customer_type,
                    "customer_subtype": r["customer_subtype"].strip(),
                    "geography": r["geography"].strip(),
                    "engagement_level": r["engagement_level"].strip(),
                    "tags": r["tags"].strip(),
                    "consent_status": consent_status,
                    "consent_source": r["consent_source"].strip(),
                    "lifecycle": _compute_lifecycle(customer_type, consent_status, 0),
                    "total_emails_sent": "0",
                    "total_emails_opened": "0",
                    "total_emails_clicked": "0",
                    "last_email_sent_at": "",
                    "last_email_opened_at": "",
                    "is_dispatched": "False",
                    "is_contacted": "False",
                    "response_notes": "",
                    "priority": r["priority"].strip(),
                    "source": r["source"].strip(),
                    "notes": "",
                    "wa_id": _phone_to_wa_id(phone),
                    "wa_consent_status": "unknown",
                    "wa_profile_name": "",
                    "last_wa_inbound_at": "",
                    "last_wa_outbound_at": "",
                    "created_at": now,
                    "updated_at": now,
                })

    for dest in DESTS:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=DEST_FIELDS)
            w.writeheader()
            w.writerows(out_rows)
        print(f"Wrote {len(out_rows):>5d} rows to {dest.relative_to(REPO)}")

    print(f"\nDuplicate emails skipped during merge: {skipped_dupe}")


if __name__ == "__main__":
    main()
