"""
Import script for all customer data files.

Files:
1. Mailchimp_Carpet Jan2025.csv - 547 potential B2B customers (carpet exporters)
2. India MasterSheet Sales_Data.csv - 130 unique past companies (existing clients) - NO EMAIL
3. Contacts_200 Yarn_Store].csv - Empty file (needs data)

Run: python scripts/import_all_data.py
"""

import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.data_manager import DataManager
from app.data_models import (
    Contact,
    CustomerType,
    CustomerSubType,
    Geography,
    EngagementLevel,
    ConsentStatus,
)


def import_mailchimp_carpet(dm: DataManager) -> dict:
    """
    Import Mailchimp Carpet Jan2025.csv - Potential B2B Customers

    547 carpet exporters from India
    """
    print("\n" + "="*60)
    print("IMPORTING: Mailchimp_Carpet Jan2025.csv (Potential B2B)")
    print("="*60)

    file_path = Path(__file__).parent.parent / "Data" / "Mailchimp_Carpet Jan2025.csv"
    df = pd.read_csv(file_path)

    contacts = []
    for _, row in df.iterrows():
        email = str(row.get("Email address(EMAIL)", "")).strip()
        if not email or email == "nan" or "@" not in email:
            continue

        # Determine geography
        country = str(row.get("Address-Country", "India")).strip()
        if pd.isna(country) or country == "nan":
            country = "India"
        geography = Geography.DOMESTIC_INDIA.value if country.lower() == "india" else Geography.INTERNATIONAL.value

        # Parse tags
        tags = str(row.get("Tags", "")).strip()
        if tags == "nan":
            tags = ""

        contact = Contact(
            email=email.lower(),
            first_name=str(row.get("First Name (F NAME)", "")).strip() if pd.notna(row.get("First Name (F NAME)")) else "",
            last_name=str(row.get("Last Name (LNAME)", "")).strip() if pd.notna(row.get("Last Name (LNAME)")) else "",
            company=str(row.get("Company Name", "")).strip() if pd.notna(row.get("Company Name")) else "",
            phone=str(row.get("Phone Number(PHONE)", "")).strip() if pd.notna(row.get("Phone Number(PHONE)")) else "",
            website=str(row.get("Website (MMERGE7)", "")).strip() if pd.notna(row.get("Website (MMERGE7)")) else "",
            address=str(row.get("Address-Combined(ADDRESS)", "")).strip() if pd.notna(row.get("Address-Combined(ADDRESS)")) else "",
            city=str(row.get("Address-City", "")).strip() if pd.notna(row.get("Address-City")) else "",
            state=str(row.get("Address-State", "")).strip() if pd.notna(row.get("Address-State")) else "",
            country=country,
            postal_code=str(row.get("Address-ZIP/Postal(ADDRESS)", "")).strip() if pd.notna(row.get("Address-ZIP/Postal(ADDRESS)")) else "",
            customer_type=CustomerType.POTENTIAL_B2B.value,
            customer_subtype=CustomerSubType.CARPET_EXPORTER.value,
            geography=geography,
            engagement_level=EngagementLevel.NEW.value,
            tags=tags,
            consent_status=ConsentStatus.PENDING.value,
            consent_source="mailchimp_carpet_jan2025",
            priority=str(row.get("Priority", "")).strip() if pd.notna(row.get("Priority")) else "",
            source="mailchimp_carpet_jan2025",
        )
        contacts.append(contact)

    result = dm.add_contacts_bulk(contacts, skip_duplicates=True)
    print(f"  Total in file: {len(df)}")
    print(f"  Valid emails: {len(contacts)}")
    print(f"  Added: {result['added']}")
    print(f"  Skipped (duplicates): {result['skipped']}")

    return result


def import_yarn_stores(dm: DataManager) -> dict:
    """
    Import Contacts_200 Yarn_Store].csv - International Yarn Stores

    359 yarn stores, mostly from US
    """
    print("\n" + "="*60)
    print("IMPORTING: Contacts_200 Yarn_Store].csv (Yarn Stores)")
    print("="*60)

    file_path = Path(__file__).parent.parent / "Data" / "Contacts_200 Yarn_Store].csv"

    # Read without header - first row is data
    df = pd.read_csv(file_path, header=None)
    df.columns = ['email', 'first_name', 'last_name', 'country', 'state', 'city', 'address', 'phone', 'postal_code', 'website', 'unknown', 'store_type']

    contacts = []
    for _, row in df.iterrows():
        email = str(row.get("email", "")).strip()
        if not email or email == "nan" or "@" not in email:
            continue

        # Determine geography
        country = str(row.get("country", "")).strip()
        if pd.isna(country) or country == "nan":
            country = "US"
        geography = Geography.DOMESTIC_INDIA.value if country.lower() == "india" else Geography.INTERNATIONAL.value

        # Determine subtype based on store_type
        store_type = str(row.get("store_type", "")).strip().lower()
        if "wholesale" in store_type:
            subtype = CustomerSubType.WHOLESALE_STORE.value
        elif "online" in store_type:
            subtype = CustomerSubType.ONLINE_STORE.value
        else:
            subtype = CustomerSubType.RETAIL_STORE.value

        # Build company name from first_name + last_name (store names)
        first = str(row.get("first_name", "")).strip() if pd.notna(row.get("first_name")) else ""
        last = str(row.get("last_name", "")).strip() if pd.notna(row.get("last_name")) else ""
        company = f"{first} {last}".strip()

        contact = Contact(
            email=email.lower(),
            first_name="",  # These are store names, not person names
            last_name="",
            company=company,
            phone=str(row.get("phone", "")).strip() if pd.notna(row.get("phone")) else "",
            website=str(row.get("website", "")).strip() if pd.notna(row.get("website")) else "",
            address=str(row.get("address", "")).strip() if pd.notna(row.get("address")) else "",
            city=str(row.get("city", "")).strip() if pd.notna(row.get("city")) else "",
            state=str(row.get("state", "")).strip() if pd.notna(row.get("state")) else "",
            country=country,
            postal_code=str(row.get("postal_code", "")).strip() if pd.notna(row.get("postal_code")) else "",
            customer_type=CustomerType.YARN_STORE.value,
            customer_subtype=subtype,
            geography=geography,
            engagement_level=EngagementLevel.NEW.value,
            tags=store_type if store_type and store_type != "nan" else "",
            consent_status=ConsentStatus.PENDING.value,
            consent_source="yarn_store_list",
            source="yarn_store_list",
        )
        contacts.append(contact)

    result = dm.add_contacts_bulk(contacts, skip_duplicates=True)
    print(f"  Total in file: {len(df)}")
    print(f"  Valid emails: {len(contacts)}")
    print(f"  Added: {result['added']}")
    print(f"  Skipped (duplicates): {result['skipped']}")

    return result


def import_existing_clients(dm: DataManager) -> dict:
    """
    Import India MasterSheet Sales_Data.csv - Existing Clients

    130 unique companies who have purchased before.
    NOTE: This file does NOT have email addresses!
    """
    print("\n" + "="*60)
    print("IMPORTING: India MasterSheet Sales_Data.csv (Existing Clients)")
    print("="*60)

    file_path = Path(__file__).parent.parent / "Data" / "India MasterSheet (10-DEC-25) Rohit.xlsx - Sales_Data.csv"
    df = pd.read_csv(file_path, usecols=range(24))

    # Get unique companies
    companies = df.groupby("Company Name").first().reset_index()

    contacts = []
    missing_emails = []

    for _, row in companies.iterrows():
        company_name = str(row.get("Company Name", "")).strip()
        if not company_name or company_name == "nan":
            continue

        # These contacts don't have email - we'll create them with placeholder
        # and flag them as needing email
        contact_person = str(row.get("Contact Person", "")).strip() if pd.notna(row.get("Contact Person")) else ""
        phone = str(row.get("Company Phone", "")).strip() if pd.notna(row.get("Company Phone")) else ""
        phone2 = str(row.get("Contact Person 2", "")).strip() if pd.notna(row.get("Contact Person 2")) else ""
        city = str(row.get("City", "")).strip() if pd.notna(row.get("City")) else ""

        # Determine subtype based on sales category
        sales_cat = str(row.get("Sales Category", "")).strip().lower() if pd.notna(row.get("Sales Category")) else ""
        fibre_type = str(row.get("Fibre Type", "")).strip() if pd.notna(row.get("Fibre Type")) else ""

        if "yarn" in sales_cat:
            subtype = CustomerSubType.TEXTILE_MANUFACTURER.value
        elif "fabric" in sales_cat:
            subtype = CustomerSubType.TEXTILE_MANUFACTURER.value
        elif "bag" in sales_cat:
            subtype = CustomerSubType.HANDICRAFT_EXPORTER.value
        else:
            subtype = CustomerSubType.OTHER.value

        # Build tags from fibre type and category
        tags = []
        if fibre_type and fibre_type != "nan":
            tags.append(fibre_type.lower())
        if sales_cat and sales_cat != "nan":
            tags.append(sales_cat.lower())

        missing_emails.append({
            "company": company_name,
            "contact_person": contact_person,
            "phone": phone,
            "phone2": phone2,
            "city": city,
            "category": sales_cat,
            "fibre_type": fibre_type,
        })

        # Create contact without email (will need to be filled later)
        contact = Contact(
            email=f"missing_{company_name.lower().replace(' ', '_')[:20]}@placeholder.local",
            first_name=contact_person.split()[0] if contact_person else "",
            last_name=" ".join(contact_person.split()[1:]) if contact_person and len(contact_person.split()) > 1 else "",
            company=company_name,
            phone=phone,
            city=city,
            country="India",
            customer_type=CustomerType.EXISTING_CLIENT.value,
            customer_subtype=subtype,
            geography=Geography.DOMESTIC_INDIA.value,
            engagement_level=EngagementLevel.WARM.value,  # They've bought before
            tags=",".join(tags),
            consent_status=ConsentStatus.PENDING.value,
            consent_source="sales_data_dec2025",
            source="sales_data_dec2025",
            notes=f"Phone2: {phone2}" if phone2 else "",
        )
        contacts.append(contact)

    result = dm.add_contacts_bulk(contacts, skip_duplicates=True)
    print(f"  Total rows in file: {len(df)}")
    print(f"  Unique companies: {len(companies)}")
    print(f"  Added: {result['added']}")
    print(f"  Skipped (duplicates): {result['skipped']}")
    print(f"\n  ⚠️  WARNING: These contacts have NO EMAIL ADDRESSES!")
    print(f"  They have placeholder emails that need to be updated.")

    return {**result, "missing_emails": missing_emails}


def generate_missing_data_report(dm: DataManager, existing_clients_result: dict):
    """Generate a CSV report of missing data."""
    print("\n" + "="*60)
    print("GENERATING: Missing Data Report")
    print("="*60)

    # Create reports directory
    reports_dir = Path(__file__).parent.parent / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Report 1: Existing clients needing email
    if existing_clients_result.get("missing_emails"):
        report_path = reports_dir / "existing_clients_need_email.csv"
        df = pd.DataFrame(existing_clients_result["missing_emails"])
        df.to_csv(report_path, index=False)
        print(f"  Created: {report_path}")
        print(f"  → {len(df)} companies need email addresses")

    # Report 2: Overall data quality
    contacts = dm.get_all_contacts()

    missing_data = {
        "missing_email": 0,
        "missing_company": 0,
        "missing_phone": 0,
        "missing_city": 0,
        "missing_website": 0,
        "placeholder_email": 0,
    }

    for contact in contacts:
        if not contact.email or "@" not in contact.email:
            missing_data["missing_email"] += 1
        if "placeholder.local" in contact.email:
            missing_data["placeholder_email"] += 1
        if not contact.company:
            missing_data["missing_company"] += 1
        if not contact.phone:
            missing_data["missing_phone"] += 1
        if not contact.city:
            missing_data["missing_city"] += 1
        if not contact.website:
            missing_data["missing_website"] += 1

    print(f"\n  Data Quality Summary ({len(contacts)} total contacts):")
    for field, count in missing_data.items():
        pct = round(count / len(contacts) * 100, 1) if contacts else 0
        print(f"    - {field}: {count} ({pct}%)")

    return missing_data


def create_separate_csvs(dm: DataManager):
    """Create separate CSV files for each customer type."""
    print("\n" + "="*60)
    print("CREATING: Separate CSV files by customer type")
    print("="*60)

    output_dir = Path(__file__).parent.parent / "data" / "by_type"
    output_dir.mkdir(parents=True, exist_ok=True)

    contacts = dm.get_all_contacts()

    # Group by customer type
    by_type = {}
    for contact in contacts:
        ct = contact.customer_type
        if ct not in by_type:
            by_type[ct] = []
        by_type[ct].append(contact)

    for customer_type, type_contacts in by_type.items():
        file_path = output_dir / f"{customer_type}.csv"

        # Convert to dicts for pandas
        rows = [c.to_dict() for c in type_contacts]
        df = pd.DataFrame(rows)

        # Reorder columns for readability
        priority_cols = ["email", "first_name", "last_name", "company", "phone", "city", "country", "customer_subtype", "tags"]
        other_cols = [c for c in df.columns if c not in priority_cols]
        df = df[priority_cols + other_cols]

        df.to_csv(file_path, index=False)
        print(f"  Created: {file_path} ({len(type_contacts)} contacts)")


def main():
    print("\n" + "="*60)
    print("HIMALAYAN FIBERS - DATA IMPORT SCRIPT")
    print("="*60)
    print(f"Started at: {datetime.now().isoformat()}")

    # Clear existing data and start fresh
    dm = DataManager()

    # Clear existing contacts (fresh import)
    contacts_file = dm.contacts_file
    if contacts_file.exists():
        print("\n  Clearing existing contacts for fresh import...")
        contacts_file.unlink()
    dm._init_files()

    # Import each file
    mailchimp_result = import_mailchimp_carpet(dm)
    yarn_store_result = import_yarn_stores(dm)
    existing_result = import_existing_clients(dm)

    # Generate reports
    generate_missing_data_report(dm, existing_result)

    # Create separate CSVs
    create_separate_csvs(dm)

    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)

    stats = dm.get_contact_stats()
    print(f"\nTotal Contacts: {stats['total']}")
    print(f"\nBy Customer Type:")
    for ct, count in stats['by_customer_type'].items():
        print(f"  - {ct}: {count}")
    print(f"\nBy Geography:")
    for geo, count in stats['by_geography'].items():
        print(f"  - {geo}: {count}")

    print("\n" + "="*60)
    print("WHAT'S MISSING")
    print("="*60)
    print("""
1. EXISTING CLIENTS (130 companies) - NEED EMAIL ADDRESSES
   → See: data/reports/existing_clients_need_email.csv
   → These are your past buyers from the Sales Data file
   → You need to provide their email addresses

2. YARN STORES - FILE IS EMPTY
   → File: Data/Contacts_200 Yarn_Store].csv is empty (0 bytes)
   → Please provide the yarn store contact data

3. INTERNATIONAL CLIENTS
   → Currently all contacts are from India
   → Add international contacts when available
    """)

    print(f"\nCompleted at: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
