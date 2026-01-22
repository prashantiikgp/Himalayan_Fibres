"""Excel contact importer service."""

import io
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Contact, ConsentStatus, ContactType

logger = get_logger(__name__)


# Column name mappings (lowercase)
COLUMN_MAPPINGS = {
    "email": ["email", "email_address", "e-mail", "mail"],
    "name": ["name", "full_name", "fullname", "contact_name", "contact"],
    "company": ["company", "company_name", "organization", "org", "business", "firm"],
    "phone": ["phone", "phone_number", "mobile", "tel", "telephone", "contact_number"],
    "country": ["country", "nation", "location"],
    "city": ["city", "town"],
    "contact_type": ["type", "contact_type", "business_type", "category"],
    "tags": ["tags", "labels", "keywords"],
}

# Contact type mappings (lowercase)
TYPE_MAPPINGS = {
    "carpet": ContactType.CARPET_EXPORTER,
    "carpet_exporter": ContactType.CARPET_EXPORTER,
    "carpet exporter": ContactType.CARPET_EXPORTER,
    "handicraft": ContactType.HANDICRAFT_EXPORTER,
    "handicraft_exporter": ContactType.HANDICRAFT_EXPORTER,
    "handicraft exporter": ContactType.HANDICRAFT_EXPORTER,
    "textile": ContactType.TEXTILE_MANUFACTURER,
    "textile_manufacturer": ContactType.TEXTILE_MANUFACTURER,
    "retailer": ContactType.RETAILER,
    "designer": ContactType.DESIGNER,
    "buyer": ContactType.BUYER,
    "producer": ContactType.PRODUCER,
    "partner": ContactType.PARTNER,
}


class ContactImporter:
    """Service for importing contacts from Excel files."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _find_column(self, df_columns: list[str], field: str) -> str | None:
        """Find the DataFrame column that matches a field."""
        lowercase_cols = [c.lower().strip() for c in df_columns]
        mappings = COLUMN_MAPPINGS.get(field, [field])

        for mapping in mappings:
            if mapping.lower() in lowercase_cols:
                idx = lowercase_cols.index(mapping.lower())
                return df_columns[idx]

        return None

    def _parse_contact_type(self, value: str | None) -> ContactType:
        """Parse a contact type string to enum."""
        if not value:
            return ContactType.OTHER

        value_lower = value.lower().strip()

        # Direct mapping
        if value_lower in TYPE_MAPPINGS:
            return TYPE_MAPPINGS[value_lower]

        # Partial matching
        for key, contact_type in TYPE_MAPPINGS.items():
            if key in value_lower:
                return contact_type

        return ContactType.OTHER

    def _parse_tags(self, value: str | None) -> list[str]:
        """Parse tags from a comma-separated string."""
        if not value or pd.isna(value):
            return []

        # Split by comma, semicolon, or pipe
        import re

        tags = re.split(r"[,;|]", str(value))
        return [tag.strip() for tag in tags if tag.strip()]

    async def import_from_excel(
        self,
        file_content: bytes,
        default_consent_status: ConsentStatus = ConsentStatus.PENDING,
        default_contact_type: ContactType = ContactType.OTHER,
    ) -> dict[str, Any]:
        """
        Import contacts from Excel file content.

        Args:
            file_content: Raw bytes of Excel file
            default_consent_status: Default consent status for imported contacts
            default_contact_type: Default contact type for imported contacts

        Returns:
            dict with total_rows, imported, skipped, errors
        """
        # Read Excel file
        try:
            df = pd.read_excel(io.BytesIO(file_content))
        except Exception as e:
            logger.error("Failed to read Excel file", error=str(e))
            return {
                "total_rows": 0,
                "imported": 0,
                "skipped": 0,
                "errors": [f"Failed to read Excel file: {str(e)}"],
            }

        if df.empty:
            return {
                "total_rows": 0,
                "imported": 0,
                "skipped": 0,
                "errors": ["Excel file is empty"],
            }

        # Find column mappings
        columns = list(df.columns)
        email_col = self._find_column(columns, "email")

        if not email_col:
            return {
                "total_rows": len(df),
                "imported": 0,
                "skipped": len(df),
                "errors": ["No email column found in Excel file"],
            }

        name_col = self._find_column(columns, "name")
        company_col = self._find_column(columns, "company")
        phone_col = self._find_column(columns, "phone")
        country_col = self._find_column(columns, "country")
        city_col = self._find_column(columns, "city")
        type_col = self._find_column(columns, "contact_type")
        tags_col = self._find_column(columns, "tags")

        logger.info(
            "Column mappings found",
            email=email_col,
            name=name_col,
            company=company_col,
            phone=phone_col,
            country=country_col,
            type=type_col,
            tags=tags_col,
        )

        # Process rows
        imported = 0
        skipped = 0
        errors = []
        existing_emails = set()

        # Get existing emails in batch
        result = await self.db.execute(select(Contact.email))
        existing_emails = {row[0].lower() for row in result.fetchall()}

        for idx, row in df.iterrows():
            try:
                # Get email
                email = str(row[email_col]).strip().lower() if pd.notna(row[email_col]) else None

                if not email or "@" not in email:
                    skipped += 1
                    continue

                # Check if exists
                if email in existing_emails:
                    skipped += 1
                    continue

                # Extract fields
                name = str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else None
                company = str(row[company_col]).strip() if company_col and pd.notna(row[company_col]) else None
                phone = str(row[phone_col]).strip() if phone_col and pd.notna(row[phone_col]) else None
                country = str(row[country_col]).strip() if country_col and pd.notna(row[country_col]) else None
                city = str(row[city_col]).strip() if city_col and pd.notna(row[city_col]) else None

                # Parse contact type
                contact_type = default_contact_type
                if type_col and pd.notna(row[type_col]):
                    contact_type = self._parse_contact_type(str(row[type_col]))

                # Parse tags
                tags = []
                if tags_col and pd.notna(row[tags_col]):
                    tags = self._parse_tags(str(row[tags_col]))

                # Collect extra columns as custom fields
                custom_fields = {}
                mapped_cols = {
                    email_col, name_col, company_col, phone_col,
                    country_col, city_col, type_col, tags_col
                }
                for col in columns:
                    if col not in mapped_cols and pd.notna(row[col]):
                        custom_fields[col] = str(row[col])

                # Create contact
                contact = Contact(
                    email=email,
                    name=name,
                    company=company,
                    phone=phone,
                    country=country,
                    city=city,
                    contact_type=contact_type,
                    tags=tags,
                    consent_status=default_consent_status,
                    consent_source="excel_import",
                    consent_timestamp=datetime.now(timezone.utc) if default_consent_status == ConsentStatus.OPTED_IN else None,
                    custom_fields=custom_fields if custom_fields else None,
                )
                self.db.add(contact)
                existing_emails.add(email)
                imported += 1

            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                skipped += 1

        # Commit all at once
        try:
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.error("Failed to commit imported contacts", error=str(e))
            return {
                "total_rows": len(df),
                "imported": 0,
                "skipped": len(df),
                "errors": [f"Database commit failed: {str(e)}"],
            }

        logger.info(
            "Excel import completed",
            total=len(df),
            imported=imported,
            skipped=skipped,
            errors=len(errors),
        )

        return {
            "total_rows": len(df),
            "imported": imported,
            "skipped": skipped,
            "errors": errors[:20],  # Limit errors to prevent huge responses
        }

    async def preview_import(
        self,
        file_content: bytes,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Preview what will be imported from an Excel file.

        Args:
            file_content: Raw bytes of Excel file
            limit: Number of rows to preview

        Returns:
            dict with columns, sample_rows, total_rows
        """
        try:
            df = pd.read_excel(io.BytesIO(file_content))
        except Exception as e:
            return {
                "error": f"Failed to read Excel file: {str(e)}",
            }

        columns = list(df.columns)

        # Map columns
        column_mapping = {}
        for field in COLUMN_MAPPINGS:
            col = self._find_column(columns, field)
            if col:
                column_mapping[field] = col

        # Get sample rows
        sample_rows = df.head(limit).to_dict(orient="records")

        return {
            "total_rows": len(df),
            "columns": columns,
            "column_mapping": column_mapping,
            "unmapped_columns": [c for c in columns if c not in column_mapping.values()],
            "sample_rows": sample_rows,
        }
