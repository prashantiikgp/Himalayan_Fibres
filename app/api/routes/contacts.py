"""Contact management endpoints."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.core.logging import get_logger
from app.db.models import Contact, ConsentStatus, ContactType
from app.services.contact_importer import ContactImporter

router = APIRouter(prefix="/contacts", tags=["contacts"])
logger = get_logger(__name__)


# ===========================================
# SCHEMAS
# ===========================================


class ContactCreate(BaseModel):
    """Schema for creating a contact."""

    email: EmailStr
    name: str | None = None
    company: str | None = None
    phone: str | None = None
    country: str | None = None
    city: str | None = None
    contact_type: ContactType = ContactType.OTHER
    tags: list[str] = []
    consent_status: ConsentStatus = ConsentStatus.PENDING
    consent_source: str | None = None
    custom_fields: dict[str, Any] = {}


class ContactUpdate(BaseModel):
    """Schema for updating a contact."""

    name: str | None = None
    company: str | None = None
    phone: str | None = None
    country: str | None = None
    city: str | None = None
    contact_type: ContactType | None = None
    tags: list[str] | None = None
    custom_fields: dict[str, Any] | None = None


class ContactResponse(BaseModel):
    """Schema for contact response."""

    id: int
    email: str
    name: str | None
    company: str | None
    phone: str | None
    country: str | None
    city: str | None
    contact_type: ContactType
    tags: list[str]
    consent_status: ConsentStatus
    consent_source: str | None
    total_emails_sent: int
    total_emails_opened: int
    total_emails_clicked: int
    created_at: datetime

    class Config:
        from_attributes = True


class ContactListResponse(BaseModel):
    """Schema for paginated contact list."""

    contacts: list[ContactResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ImportResult(BaseModel):
    """Schema for import results."""

    total_rows: int
    imported: int
    skipped: int
    errors: list[str]


# ===========================================
# ENDPOINTS
# ===========================================


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    consent_status: ConsentStatus | None = None,
    contact_type: ContactType | None = None,
    country: str | None = None,
    search: str | None = None,
):
    """List contacts with filtering and pagination."""
    query = select(Contact)

    # Apply filters
    if consent_status:
        query = query.where(Contact.consent_status == consent_status)
    if contact_type:
        query = query.where(Contact.contact_type == contact_type)
    if country:
        query = query.where(Contact.country == country)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (Contact.email.ilike(search_term))
            | (Contact.name.ilike(search_term))
            | (Contact.company.ilike(search_term))
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Contact.created_at.desc())

    result = await db.execute(query)
    contacts = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return ContactListResponse(
        contacts=[ContactResponse.model_validate(c) for c in contacts],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(contact_data: ContactCreate, db: DBSession):
    """Create a new contact."""
    # Check for existing contact
    result = await db.execute(
        select(Contact).where(Contact.email == contact_data.email)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Contact with email {contact_data.email} already exists",
        )

    contact = Contact(
        **contact_data.model_dump(),
        consent_timestamp=datetime.now(timezone.utc)
        if contact_data.consent_status == ConsentStatus.OPTED_IN
        else None,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    logger.info("Contact created", email=contact.email, id=contact.id)
    return ContactResponse.model_validate(contact)


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(contact_id: int, db: DBSession):
    """Get a specific contact by ID."""
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {contact_id} not found",
        )

    return ContactResponse.model_validate(contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(contact_id: int, contact_data: ContactUpdate, db: DBSession):
    """Update a contact."""
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {contact_id} not found",
        )

    # Update only provided fields
    update_data = contact_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)

    logger.info("Contact updated", email=contact.email, id=contact.id)
    return ContactResponse.model_validate(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: int, db: DBSession):
    """Delete a contact (GDPR forget request)."""
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {contact_id} not found",
        )

    await db.delete(contact)
    await db.commit()

    logger.info("Contact deleted", id=contact_id)


@router.post("/{contact_id}/unsubscribe", response_model=ContactResponse)
async def unsubscribe_contact(contact_id: int, db: DBSession):
    """Unsubscribe a contact."""
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {contact_id} not found",
        )

    contact.consent_status = ConsentStatus.OPTED_OUT
    await db.commit()
    await db.refresh(contact)

    logger.info("Contact unsubscribed", email=contact.email, id=contact.id)
    return ContactResponse.model_validate(contact)


@router.post("/import/excel", response_model=ImportResult)
async def import_contacts_from_excel(
    db: DBSession,
    file: UploadFile = File(...),
    default_consent_status: ConsentStatus = Query(
        ConsentStatus.PENDING,
        description="Default consent status for imported contacts",
    ),
    default_contact_type: ContactType = Query(
        ContactType.OTHER,
        description="Default contact type for imported contacts",
    ),
):
    """
    Import contacts from an Excel file.

    Expected columns (flexible mapping):
    - email (required)
    - name / full_name / contact_name
    - company / company_name / organization
    - phone / phone_number / mobile
    - country
    - city
    - type / contact_type / business_type
    - tags (comma-separated)
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )

    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an Excel file (.xlsx or .xls)",
        )

    content = await file.read()

    importer = ContactImporter(db)
    result = await importer.import_from_excel(
        content,
        default_consent_status=default_consent_status,
        default_contact_type=default_contact_type,
    )

    logger.info(
        "Excel import completed",
        total=result["total_rows"],
        imported=result["imported"],
        skipped=result["skipped"],
    )

    return ImportResult(**result)


@router.get("/stats/overview")
async def get_contact_stats(db: DBSession):
    """Get contact statistics overview."""
    # Total contacts
    total_result = await db.execute(select(func.count(Contact.id)))
    total = total_result.scalar() or 0

    # By consent status
    consent_query = select(
        Contact.consent_status, func.count(Contact.id)
    ).group_by(Contact.consent_status)
    consent_result = await db.execute(consent_query)
    by_consent = {str(row[0].value): row[1] for row in consent_result.fetchall()}

    # By contact type
    type_query = select(
        Contact.contact_type, func.count(Contact.id)
    ).group_by(Contact.contact_type)
    type_result = await db.execute(type_query)
    by_type = {str(row[0].value): row[1] for row in type_result.fetchall()}

    # By country (top 10)
    country_query = (
        select(Contact.country, func.count(Contact.id))
        .where(Contact.country.isnot(None))
        .group_by(Contact.country)
        .order_by(func.count(Contact.id).desc())
        .limit(10)
    )
    country_result = await db.execute(country_query)
    by_country = {row[0]: row[1] for row in country_result.fetchall()}

    return {
        "total_contacts": total,
        "by_consent_status": by_consent,
        "by_contact_type": by_type,
        "by_country_top10": by_country,
    }
