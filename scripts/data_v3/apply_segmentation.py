"""
Add segmentation columns (customer_type, customer_subtype, geography,
engagement_level, tags, consent_status, consent_source, priority, source)
to each Data_v3 CSV based on the source category.

Tags include a dynamic `name_fallback` flag when first_name was set to the
company name — useful for templates that should pick a different greeting
in that case.

Idempotent: re-running overwrites the segmentation columns from scratch.
"""
from __future__ import annotations

import csv
from pathlib import Path

DATA_DIR = Path("Data/Data_v3")

# Schema: original 8 columns + 8 segmentation columns
OUTPUT_FIELDS = [
    "email", "phone", "first_name", "last_name", "company", "country",
    "customer_type", "customer_subtype", "geography", "engagement_level",
    "consent_status", "consent_source", "priority", "source",
    "tags",
    "category", "source_file",
]

# Per-source-file segmentation defaults
PROFILES: dict[str, dict] = {
    "01_existing_clients.csv": {
        "customer_type": "existing_client",
        "customer_subtype": "",
        "geography": "domestic_india",
        "engagement_level": "warm",
        "consent_status": "granted",
        "consent_source": "existing_relationship",
        "priority": "high",
        "source": "existing_client_list",
        "base_tags": [],
    },
    "02_lapsed_clients.csv": {
        "customer_type": "existing_client",
        "customer_subtype": "lapsed",
        "geography": "domestic_india",
        "engagement_level": "cold",
        "consent_status": "granted",
        "consent_source": "prior_customer",
        "priority": "high",
        "source": "lapsed_client_list",
        "base_tags": ["reactivation"],
    },
    "03_carpet_exporters_india.csv": {
        "customer_type": "potential_b2b",
        "customer_subtype": "carpet_exporter",
        "geography": "domestic_india",
        "engagement_level": "new",
        "consent_status": "pending",
        "consent_source": "cepc_directory",
        "priority": "medium",
        "source": "carpet_exporter_directory",
        "base_tags": [],
    },
    "04_yarn_stores_international.csv": {
        "customer_type": "yarn_store",
        "customer_subtype": "retail_store",
        "geography": "international",
        "engagement_level": "new",
        "consent_status": "pending",
        "consent_source": "yarn_store_directory",
        "priority": "medium",
        "source": "yarn_store_directory",
        "base_tags": [],
    },
}

# Country-specific tag — used for language selection in templates
# (e.g. Hinglish for India, English for USA/Netherlands)
COUNTRY_TAGS = {
    "usa": ["usa"],
    "united states": ["usa"],
    "netherlands": ["netherlands"],
    "india": ["india"],
}


def country_tags(country: str) -> list[str]:
    return COUNTRY_TAGS.get(country.strip().lower(), [])


def per_row_tags(row: dict, base: list[str]) -> str:
    tags = list(base)
    tags += country_tags(row.get("country", ""))

    # name_fallback: first_name was set to the company name (no real
    # contact name found). Templates can branch on this.
    fn = row.get("first_name", "").strip()
    co = row.get("company", "").strip()
    if fn and co and fn == co:
        tags.append("name_fallback")
    elif fn:
        tags.append("named_contact")

    if row.get("last_name", "").strip():
        tags.append("has_full_name")

    # WhatsApp readiness: full + country code present
    phone = row.get("phone", "").strip()
    if phone.startswith("+") and len(phone) >= 10:
        tags.append("whatsapp_ready")

    # Dedup, preserve order
    seen = set()
    out = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return ",".join(out)


def process(filename: str, profile: dict) -> tuple[int, int, int]:
    path = DATA_DIR / filename
    rows = list(csv.DictReader(open(path)))
    named = 0
    fallback = 0
    wapp = 0
    for r in rows:
        r["customer_type"] = profile["customer_type"]
        r["customer_subtype"] = profile["customer_subtype"]
        r["geography"] = profile["geography"]
        r["engagement_level"] = profile["engagement_level"]
        r["consent_status"] = profile["consent_status"]
        r["consent_source"] = profile["consent_source"]
        r["priority"] = profile["priority"]
        r["source"] = profile["source"]
        r["tags"] = per_row_tags(r, profile["base_tags"])

        if "name_fallback" in r["tags"].split(","):
            fallback += 1
        if "named_contact" in r["tags"].split(","):
            named += 1
        if "whatsapp_ready" in r["tags"].split(","):
            wapp += 1

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS,
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    return len(rows), named, fallback


def main() -> None:
    print(f"{'File':40s} {'Rows':>5s} {'Named':>6s} {'Fallback':>9s}")
    print("-" * 70)
    for fname, prof in PROFILES.items():
        total, named, fallback = process(fname, prof)
        print(f"{fname:40s} {total:>5d} {named:>6d} {fallback:>9d}")


if __name__ == "__main__":
    main()
