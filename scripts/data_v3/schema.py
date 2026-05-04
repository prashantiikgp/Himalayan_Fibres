"""Canonical slim record for Data v3.

Only the fields we will actually segment, personalize, or contact on:
- identity:     email, phone (= WhatsApp), first_name, last_name, company
- segmentation: country, category
- provenance:   source_file
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    EXISTING_CLIENT = "existing_client"
    LAPSED_CLIENT = "lapsed_client"
    CARPET_EXPORTER_LEAD = "carpet_exporter_lead"
    YARN_STORE_LEAD = "yarn_store_lead"


CATEGORY_PRIORITY: dict[Category, int] = {
    Category.EXISTING_CLIENT: 0,
    Category.LAPSED_CLIENT: 1,
    Category.CARPET_EXPORTER_LEAD: 2,
    Category.YARN_STORE_LEAD: 3,
}


class ContactV3(BaseModel):
    email: str | None = None
    phone: str | None = None
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    country: str = ""
    category: Category
    source_file: str

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str | None) -> str | None:
        if not v:
            return None
        v = v.strip().lower()
        return v or None

    @field_validator("first_name", "last_name", "company", "country")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()

    def is_reachable(self) -> bool:
        """A contact must have email or phone — otherwise we can't talk to them."""
        return bool(self.email) or bool(self.phone)

    def dedup_key_email(self) -> str | None:
        return self.email

    def dedup_key_phone(self) -> str | None:
        if not self.phone:
            return None
        digits = "".join(ch for ch in self.phone if ch.isdigit())
        return digits[-10:] if len(digits) >= 10 else None

    def dedup_key_company(self) -> str | None:
        if not self.company:
            return None
        norm = "".join(ch for ch in self.company.lower() if ch.isalnum())
        return norm or None
