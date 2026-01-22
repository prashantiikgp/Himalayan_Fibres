"""Segment management endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.core.logging import get_logger
from app.db.models import Contact, ConsentStatus, ContactType, Segment

router = APIRouter(prefix="/segments", tags=["segments"])
logger = get_logger(__name__)


# ===========================================
# SCHEMAS
# ===========================================


class SegmentRules(BaseModel):
    """Schema for segment rules.

    All rules are combined with AND logic.
    Each rule can have multiple values (OR within the rule).
    """

    contact_types: list[ContactType] | None = None
    countries: list[str] | None = None
    tags: list[str] | None = None
    consent_statuses: list[ConsentStatus] | None = None
    has_opened_email: bool | None = None
    has_clicked_email: bool | None = None
    min_emails_sent: int | None = None
    max_emails_sent: int | None = None


class SegmentCreate(BaseModel):
    """Schema for creating a segment."""

    name: str
    description: str | None = None
    rules: SegmentRules


class SegmentUpdate(BaseModel):
    """Schema for updating a segment."""

    name: str | None = None
    description: str | None = None
    rules: SegmentRules | None = None
    is_active: bool | None = None


class SegmentResponse(BaseModel):
    """Schema for segment response."""

    id: int
    name: str
    description: str | None
    rules: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    contact_count: int | None = None

    class Config:
        from_attributes = True


class SegmentListResponse(BaseModel):
    """Schema for segment list."""

    segments: list[SegmentResponse]
    total: int


class SegmentContactPreview(BaseModel):
    """Preview of contacts in a segment."""

    segment_id: int
    segment_name: str
    total_contacts: int
    sample_contacts: list[dict[str, Any]]


# ===========================================
# HELPER FUNCTIONS
# ===========================================


async def count_segment_contacts(db: DBSession, segment: Segment) -> int:
    """Count contacts matching segment rules."""
    from app.services.segmentation import build_segment_query

    query = build_segment_query(segment.rules)
    count_query = select(func.count()).select_from(query.subquery())
    result = await db.execute(count_query)
    return result.scalar() or 0


# ===========================================
# ENDPOINTS
# ===========================================


@router.get("", response_model=SegmentListResponse)
async def list_segments(
    db: DBSession,
    is_active: bool | None = True,
    include_counts: bool = Query(False, description="Include contact counts (slower)"),
):
    """List all segments."""
    query = select(Segment)

    if is_active is not None:
        query = query.where(Segment.is_active == is_active)

    query = query.order_by(Segment.name)

    result = await db.execute(query)
    segments = result.scalars().all()

    segment_responses = []
    for segment in segments:
        response = SegmentResponse.model_validate(segment)
        if include_counts:
            response.contact_count = await count_segment_contacts(db, segment)
        segment_responses.append(response)

    return SegmentListResponse(
        segments=segment_responses,
        total=len(segment_responses),
    )


@router.post("", response_model=SegmentResponse, status_code=status.HTTP_201_CREATED)
async def create_segment(segment_data: SegmentCreate, db: DBSession):
    """Create a new segment."""
    segment = Segment(
        name=segment_data.name,
        description=segment_data.description,
        rules=segment_data.rules.model_dump(exclude_none=True),
    )
    db.add(segment)
    await db.commit()
    await db.refresh(segment)

    # Count matching contacts
    contact_count = await count_segment_contacts(db, segment)

    response = SegmentResponse.model_validate(segment)
    response.contact_count = contact_count

    logger.info(
        "Segment created",
        name=segment.name,
        id=segment.id,
        contact_count=contact_count,
    )
    return response


@router.get("/{segment_id}", response_model=SegmentResponse)
async def get_segment(segment_id: int, db: DBSession):
    """Get a specific segment by ID."""
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment {segment_id} not found",
        )

    response = SegmentResponse.model_validate(segment)
    response.contact_count = await count_segment_contacts(db, segment)

    return response


@router.patch("/{segment_id}", response_model=SegmentResponse)
async def update_segment(segment_id: int, segment_data: SegmentUpdate, db: DBSession):
    """Update a segment."""
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment {segment_id} not found",
        )

    update_data = segment_data.model_dump(exclude_unset=True)

    # Handle rules specially
    if "rules" in update_data and update_data["rules"]:
        update_data["rules"] = segment_data.rules.model_dump(exclude_none=True)

    for field, value in update_data.items():
        setattr(segment, field, value)

    await db.commit()
    await db.refresh(segment)

    response = SegmentResponse.model_validate(segment)
    response.contact_count = await count_segment_contacts(db, segment)

    logger.info("Segment updated", name=segment.name, id=segment.id)
    return response


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(segment_id: int, db: DBSession):
    """Delete a segment."""
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment {segment_id} not found",
        )

    await db.delete(segment)
    await db.commit()

    logger.info("Segment deleted", id=segment_id)


@router.get("/{segment_id}/contacts", response_model=SegmentContactPreview)
async def preview_segment_contacts(
    segment_id: int,
    db: DBSession,
    limit: int = Query(20, ge=1, le=100),
):
    """Preview contacts in a segment."""
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment {segment_id} not found",
        )

    from app.services.segmentation import get_segment_contacts

    contacts = await get_segment_contacts(db, segment_id, limit=limit)
    total = await count_segment_contacts(db, segment)

    return SegmentContactPreview(
        segment_id=segment.id,
        segment_name=segment.name,
        total_contacts=total,
        sample_contacts=[
            {
                "id": c.id,
                "email": c.email,
                "name": c.name,
                "company": c.company,
                "country": c.country,
                "contact_type": c.contact_type.value,
                "tags": c.tags or [],
            }
            for c in contacts
        ],
    )


@router.post("/preview-rules", response_model=SegmentContactPreview)
async def preview_segment_rules(
    rules: SegmentRules,
    db: DBSession,
    limit: int = Query(20, ge=1, le=100),
):
    """Preview contacts matching segment rules (without creating segment)."""
    from app.services.segmentation import build_segment_query

    rules_dict = rules.model_dump(exclude_none=True)
    query = build_segment_query(rules_dict).limit(limit)

    result = await db.execute(query)
    contacts = result.scalars().all()

    # Count total
    count_query = select(func.count()).select_from(
        build_segment_query(rules_dict).subquery()
    )
    total = (await db.execute(count_query)).scalar() or 0

    return SegmentContactPreview(
        segment_id=0,
        segment_name="Preview",
        total_contacts=total,
        sample_contacts=[
            {
                "id": c.id,
                "email": c.email,
                "name": c.name,
                "company": c.company,
                "country": c.country,
                "contact_type": c.contact_type.value,
                "tags": c.tags or [],
            }
            for c in contacts
        ],
    )


# ===========================================
# PREDEFINED SEGMENTS
# ===========================================


@router.post("/create-defaults")
async def create_default_segments(db: DBSession):
    """Create default segments for common use cases."""
    default_segments = [
        {
            "name": "All Opted-In Contacts",
            "description": "All contacts who have opted in to receive emails",
            "rules": {"consent_statuses": [ConsentStatus.OPTED_IN.value]},
        },
        {
            "name": "Carpet Exporters",
            "description": "All carpet exporter contacts",
            "rules": {
                "contact_types": [ContactType.CARPET_EXPORTER.value],
                "consent_statuses": [ConsentStatus.OPTED_IN.value],
            },
        },
        {
            "name": "Handicraft Exporters",
            "description": "All handicraft exporter contacts",
            "rules": {
                "contact_types": [ContactType.HANDICRAFT_EXPORTER.value],
                "consent_statuses": [ConsentStatus.OPTED_IN.value],
            },
        },
        {
            "name": "India Contacts",
            "description": "All contacts from India",
            "rules": {
                "countries": ["India"],
                "consent_statuses": [ConsentStatus.OPTED_IN.value],
            },
        },
        {
            "name": "International Contacts",
            "description": "All contacts outside India",
            "rules": {
                "consent_statuses": [ConsentStatus.OPTED_IN.value],
                # Note: This needs custom logic - contacts NOT in India
            },
        },
        {
            "name": "Engaged Contacts",
            "description": "Contacts who have opened at least one email",
            "rules": {
                "has_opened_email": True,
                "consent_statuses": [ConsentStatus.OPTED_IN.value],
            },
        },
        {
            "name": "Inactive Contacts",
            "description": "Contacts who haven't opened any emails",
            "rules": {
                "has_opened_email": False,
                "consent_statuses": [ConsentStatus.OPTED_IN.value],
            },
        },
    ]

    created = []
    skipped = []

    for seg_data in default_segments:
        # Check if segment with same name exists
        result = await db.execute(
            select(Segment).where(Segment.name == seg_data["name"])
        )
        existing = result.scalar_one_or_none()

        if existing:
            skipped.append(seg_data["name"])
            continue

        segment = Segment(
            name=seg_data["name"],
            description=seg_data["description"],
            rules=seg_data["rules"],
        )
        db.add(segment)
        created.append(seg_data["name"])

    await db.commit()

    logger.info(
        "Default segments created",
        created=len(created),
        skipped=len(skipped),
    )

    return {
        "created": created,
        "skipped": skipped,
    }
