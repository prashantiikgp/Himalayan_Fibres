"""Per-source extractors.

Each function takes the path to a Data_v2 spreadsheet and returns a
list[ContactV3] with the right `category`, `source_file`, and field
mapping. All field-level cleaning is delegated to `normalize`.

Source choices (other sheets are intentionally ignored — they are
either subsets, less-clean exports, or non-contact reference data):

    Existing Client.xlsx        → 'Existing Client'
    Churned client.xlsx         → 'Churned Client'
    Indian_Carpet_Exporter.xlsx → 'Members'   (richer; has source provenance)
    International Yarn Store.xlsx → 'Sheet1'  (richer; has Category, Telephone)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .normalize import (
    clean_company,
    clean_country,
    clean_email,
    clean_phone,
    clean_str,
    title_name,
)
from .schema import Category, ContactV3


def _split_name(full: str) -> tuple[str, str]:
    parts = clean_str(full).split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return title_name(parts[0]), ""
    return title_name(parts[0]), title_name(" ".join(parts[1:]))


def extract_existing_clients(path: Path) -> list[ContactV3]:
    df = pd.read_excel(path, sheet_name="Existing Client")
    out: list[ContactV3] = []
    for _, row in df.iterrows():
        c = ContactV3(
            email=clean_email(row.get("Email address(EMAIL)")),
            phone=clean_phone(row.get("Phone Number(PHONE)"), default_country_code="91"),
            first_name=title_name(row.get("First Name(FNAME)")),
            last_name=title_name(row.get("Last Name(LNAME)")),
            company=clean_company(row.get("Company name")),
            country=clean_country(row.get("Address-Country")) or "India",
            category=Category.EXISTING_CLIENT,
            source_file="Existing Client.xlsx",
        )
        if c.is_reachable() or c.company:
            out.append(c)
    return out


def extract_lapsed_clients(path: Path) -> list[ContactV3]:
    df = pd.read_excel(path, sheet_name="Churned Client")
    out: list[ContactV3] = []
    for _, row in df.iterrows():
        c = ContactV3(
            email=clean_email(row.get("Email address(EMAIL)")),
            phone=clean_phone(row.get("Phone Number(PHONE)"), default_country_code="91"),
            first_name=title_name(row.get("First Name(FNAME)")),
            last_name=title_name(row.get("Last Name(LNAME)")),
            company=clean_company(row.get("Company name")),
            country=clean_country(row.get("Address-Country")) or "India",
            category=Category.LAPSED_CLIENT,
            source_file="Churned client.xlsx",
        )
        if c.is_reachable() or c.company:
            out.append(c)
    return out


def extract_carpet_exporters(path: Path) -> list[ContactV3]:
    df = pd.read_excel(path, sheet_name="Members")
    out: list[ContactV3] = []
    for _, row in df.iterrows():
        c = ContactV3(
            email=clean_email(row.get("email")),
            phone=clean_phone(row.get("phone"), default_country_code="91"),
            first_name=title_name(row.get("first_name")),
            last_name=title_name(row.get("last_name")),
            company=clean_company(row.get("company")),
            country="India",
            category=Category.CARPET_EXPORTER_LEAD,
            source_file="Indian_Carpet_Exporter.xlsx",
        )
        if c.is_reachable() or c.company:
            out.append(c)
    return out


def extract_yarn_stores(path: Path) -> list[ContactV3]:
    df = pd.read_excel(path, sheet_name="Sheet1")
    out: list[ContactV3] = []
    for _, row in df.iterrows():
        first, last = _split_name("")
        company = clean_company(row.get("Name"))
        # Yarn Sheet1 has no name column; the 'Name' is the store name.
        # Phones are already in '+1 907-...' or similar with explicit country code.
        phone_raw = clean_str(row.get("Telephone"))
        phone = clean_phone(phone_raw) if phone_raw.startswith("+") else clean_phone(phone_raw, default_country_code="1")
        c = ContactV3(
            email=clean_email(row.get("Email")),
            phone=phone,
            first_name=first,
            last_name=last,
            company=company,
            country=_yarn_country_from_input(row.get("Input")) or "USA",
            category=Category.YARN_STORE_LEAD,
            source_file="International Yarn Store.xlsx",
        )
        if c.is_reachable() or c.company:
            out.append(c)
    return out


def _yarn_country_from_input(v) -> str:
    """Sheet1's `Input` column is a Google Maps search URL. Most are
    '...yarn+store+in+<state>,+USA/...' but some are '...in+Netherlands/'.
    Pull out the country chunk so we don't blanket-tag everything as USA.
    """
    s = clean_str(v).lower()
    if not s:
        return ""
    if "+usa" in s or ",+usa" in s or "usa/" in s:
        return "USA"
    for needle, country in (
        ("netherlands", "Netherlands"),
        ("united+kingdom", "UK"),
        ("canada", "Canada"),
        ("australia", "Australia"),
        ("germany", "Germany"),
        ("france", "France"),
    ):
        if needle in s:
            return country
    return ""
