"""Campaign management endpoints."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import (
    Campaign,
    CampaignStatus,
    Contact,
    ConsentStatus,
    EmailTemplate,
    Segment,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
logger = get_logger(__name__)


# ===========================================
# SCHEMAS
# ===========================================


class CampaignCreate(BaseModel):
    """Schema for creating a campaign."""

    name: str
    description: str | None = None
    subject: str
    html_content: str
    plain_text_content: str | None = None
    segment_id: int | None = None
    template_id: int | None = None
    scheduled_at: datetime | None = None
    is_ai_generated: bool = False
    ai_generation_prompt: str | None = None


class CampaignUpdate(BaseModel):
    """Schema for updating a campaign."""

    name: str | None = None
    description: str | None = None
    subject: str | None = None
    html_content: str | None = None
    plain_text_content: str | None = None
    segment_id: int | None = None
    scheduled_at: datetime | None = None


class CampaignResponse(BaseModel):
    """Schema for campaign response."""

    id: int
    name: str
    description: str | None
    subject: str
    html_content: str
    plain_text_content: str | None
    segment_id: int | None
    template_id: int | None
    status: CampaignStatus
    scheduled_at: datetime | None
    approved_at: datetime | None
    approved_by: str | None
    sent_at: datetime | None
    total_recipients: int
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_bounced: int
    total_unsubscribed: int
    is_ai_generated: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CampaignListResponse(BaseModel):
    """Schema for paginated campaign list."""

    campaigns: list[CampaignResponse]
    total: int
    page: int
    page_size: int


class ApprovalRequest(BaseModel):
    """Schema for campaign approval."""

    approved_by: str


class CampaignAnalytics(BaseModel):
    """Schema for campaign analytics."""

    campaign_id: int
    campaign_name: str
    total_recipients: int
    total_sent: int
    total_delivered: int
    total_opened: int
    total_clicked: int
    total_bounced: int
    total_unsubscribed: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    bounce_rate: float
    unsubscribe_rate: float


# ===========================================
# ENDPOINTS
# ===========================================


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: CampaignStatus | None = None,
):
    """List campaigns with filtering and pagination."""
    query = select(Campaign)

    if status_filter:
        query = query.where(Campaign.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Campaign.created_at.desc())

    result = await db.execute(query)
    campaigns = result.scalars().all()

    return CampaignListResponse(
        campaigns=[CampaignResponse.model_validate(c) for c in campaigns],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(campaign_data: CampaignCreate, db: DBSession):
    """Create a new campaign."""
    # Validate segment if provided
    if campaign_data.segment_id:
        result = await db.execute(
            select(Segment).where(Segment.id == campaign_data.segment_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segment {campaign_data.segment_id} not found",
            )

    # Validate template if provided
    if campaign_data.template_id:
        result = await db.execute(
            select(EmailTemplate).where(EmailTemplate.id == campaign_data.template_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template {campaign_data.template_id} not found",
            )

    campaign = Campaign(**campaign_data.model_dump())
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    logger.info("Campaign created", name=campaign.name, id=campaign.id)
    return CampaignResponse.model_validate(campaign)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: int, db: DBSession):
    """Get a specific campaign by ID."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    return CampaignResponse.model_validate(campaign)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int, campaign_data: CampaignUpdate, db: DBSession
):
    """Update a campaign (only if in draft status)."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    if campaign.status not in [CampaignStatus.DRAFT, CampaignStatus.PENDING_APPROVAL]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit campaign in status {campaign.status.value}",
        )

    update_data = campaign_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)

    await db.commit()
    await db.refresh(campaign)

    logger.info("Campaign updated", name=campaign.name, id=campaign.id)
    return CampaignResponse.model_validate(campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: int, db: DBSession):
    """Delete a campaign (only if in draft status)."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    if campaign.status != CampaignStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only delete campaigns in draft status",
        )

    await db.delete(campaign)
    await db.commit()

    logger.info("Campaign deleted", id=campaign_id)


@router.post("/{campaign_id}/submit-for-approval", response_model=CampaignResponse)
async def submit_for_approval(campaign_id: int, db: DBSession):
    """Submit a campaign for approval."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    if campaign.status != CampaignStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only submit draft campaigns for approval",
        )

    # Calculate total recipients
    if campaign.segment_id:
        from app.services.segmentation import get_segment_contacts

        contacts = await get_segment_contacts(db, campaign.segment_id)
        campaign.total_recipients = len(contacts)
    else:
        # All opted-in contacts
        count_result = await db.execute(
            select(func.count(Contact.id)).where(
                Contact.consent_status == ConsentStatus.OPTED_IN
            )
        )
        campaign.total_recipients = count_result.scalar() or 0

    campaign.status = CampaignStatus.PENDING_APPROVAL
    await db.commit()
    await db.refresh(campaign)

    logger.info(
        "Campaign submitted for approval",
        name=campaign.name,
        id=campaign.id,
        recipients=campaign.total_recipients,
    )
    return CampaignResponse.model_validate(campaign)


@router.post("/{campaign_id}/approve", response_model=CampaignResponse)
async def approve_campaign(
    campaign_id: int,
    approval: ApprovalRequest,
    db: DBSession,
):
    """Approve a campaign for sending."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    if campaign.status != CampaignStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only approve campaigns pending approval",
        )

    campaign.status = CampaignStatus.APPROVED
    campaign.approved_at = datetime.now(timezone.utc)
    campaign.approved_by = approval.approved_by
    await db.commit()
    await db.refresh(campaign)

    logger.info(
        "Campaign approved",
        name=campaign.name,
        id=campaign.id,
        approved_by=approval.approved_by,
    )
    return CampaignResponse.model_validate(campaign)


@router.post("/{campaign_id}/schedule", response_model=CampaignResponse)
async def schedule_campaign(
    campaign_id: int,
    scheduled_at: datetime = Query(..., description="Scheduled send time (UTC)"),
    db: DBSession = None,
):
    """Schedule an approved campaign for sending."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    if campaign.status != CampaignStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only schedule approved campaigns",
        )

    if scheduled_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduled time must be in the future",
        )

    campaign.scheduled_at = scheduled_at
    campaign.status = CampaignStatus.SCHEDULED
    await db.commit()
    await db.refresh(campaign)

    # Queue the campaign send task
    from app.workers.tasks import send_campaign

    delay_seconds = (scheduled_at - datetime.now(timezone.utc)).total_seconds()
    send_campaign.apply_async(
        kwargs={"campaign_id": campaign.id},
        countdown=max(0, delay_seconds),
    )

    logger.info(
        "Campaign scheduled",
        name=campaign.name,
        id=campaign.id,
        scheduled_at=scheduled_at.isoformat(),
    )
    return CampaignResponse.model_validate(campaign)


@router.post("/{campaign_id}/send-now", response_model=CampaignResponse)
async def send_campaign_now(campaign_id: int, db: DBSession):
    """Send an approved campaign immediately."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    if campaign.status not in [CampaignStatus.APPROVED, CampaignStatus.SCHEDULED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only send approved or scheduled campaigns",
        )

    campaign.status = CampaignStatus.SENDING
    await db.commit()

    # Queue the campaign send task immediately
    from app.workers.tasks import send_campaign

    send_campaign.delay(campaign_id=campaign.id)

    await db.refresh(campaign)

    logger.info("Campaign send initiated", name=campaign.name, id=campaign.id)
    return CampaignResponse.model_validate(campaign)


@router.post("/{campaign_id}/cancel", response_model=CampaignResponse)
async def cancel_campaign(campaign_id: int, db: DBSession):
    """Cancel a scheduled campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    if campaign.status not in [
        CampaignStatus.SCHEDULED,
        CampaignStatus.PENDING_APPROVAL,
        CampaignStatus.APPROVED,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel campaign in status {campaign.status.value}",
        )

    campaign.status = CampaignStatus.CANCELLED
    await db.commit()
    await db.refresh(campaign)

    logger.info("Campaign cancelled", name=campaign.name, id=campaign.id)
    return CampaignResponse.model_validate(campaign)


@router.get("/{campaign_id}/analytics", response_model=CampaignAnalytics)
async def get_campaign_analytics(campaign_id: int, db: DBSession):
    """Get detailed analytics for a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    # Calculate rates
    total_sent = campaign.total_sent or 1  # Avoid division by zero
    delivery_rate = (campaign.total_delivered / total_sent * 100) if total_sent > 0 else 0
    open_rate = (campaign.total_opened / campaign.total_delivered * 100) if campaign.total_delivered > 0 else 0
    click_rate = (campaign.total_clicked / campaign.total_opened * 100) if campaign.total_opened > 0 else 0
    bounce_rate = (campaign.total_bounced / total_sent * 100) if total_sent > 0 else 0
    unsubscribe_rate = (campaign.total_unsubscribed / total_sent * 100) if total_sent > 0 else 0

    return CampaignAnalytics(
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        total_recipients=campaign.total_recipients,
        total_sent=campaign.total_sent,
        total_delivered=campaign.total_delivered,
        total_opened=campaign.total_opened,
        total_clicked=campaign.total_clicked,
        total_bounced=campaign.total_bounced,
        total_unsubscribed=campaign.total_unsubscribed,
        delivery_rate=round(delivery_rate, 2),
        open_rate=round(open_rate, 2),
        click_rate=round(click_rate, 2),
        bounce_rate=round(bounce_rate, 2),
        unsubscribe_rate=round(unsubscribe_rate, 2),
    )


@router.get("/{campaign_id}/preview-recipients")
async def preview_recipients(
    campaign_id: int,
    db: DBSession,
    limit: int = Query(10, ge=1, le=100),
):
    """Preview recipients for a campaign (sample contacts)."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign {campaign_id} not found",
        )

    if campaign.segment_id:
        from app.services.segmentation import get_segment_contacts

        contacts = await get_segment_contacts(db, campaign.segment_id, limit=limit)
    else:
        result = await db.execute(
            select(Contact)
            .where(Contact.consent_status == ConsentStatus.OPTED_IN)
            .limit(limit)
        )
        contacts = result.scalars().all()

    return {
        "campaign_id": campaign.id,
        "segment_id": campaign.segment_id,
        "sample_recipients": [
            {
                "id": c.id,
                "email": c.email,
                "name": c.name,
                "company": c.company,
            }
            for c in contacts
        ],
        "total_recipients": campaign.total_recipients,
    }
