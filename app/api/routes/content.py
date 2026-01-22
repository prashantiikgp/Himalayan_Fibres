"""AI content generation endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DBSession
from app.core.logging import get_logger
from app.db.models import ContentDraft

router = APIRouter(prefix="/content", tags=["content"])
logger = get_logger(__name__)


# ===========================================
# SCHEMAS
# ===========================================


class EmailGenerationRequest(BaseModel):
    """Schema for email content generation request."""

    topic: str
    email_type: str = "educational"  # educational, product_update, company_news
    tone: str = "professional"  # professional, friendly, formal
    target_audience: str | None = None
    key_points: list[str] = []
    include_cta: bool = True
    cta_text: str | None = None
    cta_url: str | None = None


class BlogGenerationRequest(BaseModel):
    """Schema for blog content generation request."""

    topic: str
    target_keywords: list[str] = []
    include_faq: bool = True
    include_product_links: bool = True
    word_count_target: int = 800


class ContentDraftResponse(BaseModel):
    """Schema for content draft response."""

    id: int
    content_type: str
    title: str
    subject: str | None
    body: str
    html_body: str | None
    prompt_used: str
    research_sources: list[str]
    model_used: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ContentDraftListResponse(BaseModel):
    """Schema for content draft list."""

    drafts: list[ContentDraftResponse]
    total: int


class ReviewRequest(BaseModel):
    """Schema for content review."""

    status: str  # approved, rejected
    reviewed_by: str
    review_notes: str | None = None


# ===========================================
# ENDPOINTS
# ===========================================


@router.post("/generate/email", response_model=ContentDraftResponse)
async def generate_email_content(
    request: EmailGenerationRequest,
    db: DBSession,
):
    """
    Generate AI email content based on topic and parameters.

    Uses Tavily for research and Claude for writing.
    """
    from app.services.content_generator import ContentGenerator

    generator = ContentGenerator()

    try:
        result = await generator.generate_email(
            topic=request.topic,
            email_type=request.email_type,
            tone=request.tone,
            target_audience=request.target_audience,
            key_points=request.key_points,
            include_cta=request.include_cta,
            cta_text=request.cta_text,
            cta_url=request.cta_url,
        )
    except Exception as e:
        logger.error("Email generation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content generation failed: {str(e)}",
        )

    # Store draft
    draft = ContentDraft(
        content_type="email",
        title=result["title"],
        subject=result["subject"],
        body=result["body"],
        html_body=result.get("html_body"),
        prompt_used=result["prompt_used"],
        research_sources=result.get("sources", []),
        model_used=result.get("model", "claude-3-sonnet"),
        status="pending_review",
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)

    logger.info("Email content generated", draft_id=draft.id, topic=request.topic)
    return ContentDraftResponse.model_validate(draft)


@router.post("/generate/blog", response_model=ContentDraftResponse)
async def generate_blog_content(
    request: BlogGenerationRequest,
    db: DBSession,
):
    """
    Generate AI blog content based on topic and parameters.

    Uses Tavily for research and Claude for writing.
    """
    from app.services.content_generator import ContentGenerator

    generator = ContentGenerator()

    try:
        result = await generator.generate_blog(
            topic=request.topic,
            target_keywords=request.target_keywords,
            include_faq=request.include_faq,
            include_product_links=request.include_product_links,
            word_count_target=request.word_count_target,
        )
    except Exception as e:
        logger.error("Blog generation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Content generation failed: {str(e)}",
        )

    # Store draft
    draft = ContentDraft(
        content_type="blog",
        title=result["title"],
        body=result["body"],
        html_body=result.get("html_body"),
        prompt_used=result["prompt_used"],
        research_sources=result.get("sources", []),
        model_used=result.get("model", "claude-3-sonnet"),
        status="pending_review",
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)

    logger.info("Blog content generated", draft_id=draft.id, topic=request.topic)
    return ContentDraftResponse.model_validate(draft)


@router.get("/drafts", response_model=ContentDraftListResponse)
async def list_drafts(
    db: DBSession,
    content_type: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
):
    """List content drafts."""
    query = select(ContentDraft)

    if content_type:
        query = query.where(ContentDraft.content_type == content_type)
    if status_filter:
        query = query.where(ContentDraft.status == status_filter)

    query = query.order_by(ContentDraft.created_at.desc())

    result = await db.execute(query)
    drafts = result.scalars().all()

    return ContentDraftListResponse(
        drafts=[ContentDraftResponse.model_validate(d) for d in drafts],
        total=len(drafts),
    )


@router.get("/drafts/{draft_id}", response_model=ContentDraftResponse)
async def get_draft(draft_id: int, db: DBSession):
    """Get a specific content draft."""
    result = await db.execute(
        select(ContentDraft).where(ContentDraft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found",
        )

    return ContentDraftResponse.model_validate(draft)


@router.post("/drafts/{draft_id}/review", response_model=ContentDraftResponse)
async def review_draft(
    draft_id: int,
    review: ReviewRequest,
    db: DBSession,
):
    """Review and approve/reject a content draft."""
    result = await db.execute(
        select(ContentDraft).where(ContentDraft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found",
        )

    if review.status not in ["approved", "rejected"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be 'approved' or 'rejected'",
        )

    draft.status = review.status
    draft.reviewed_by = review.reviewed_by
    draft.review_notes = review.review_notes
    draft.reviewed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(draft)

    logger.info(
        "Draft reviewed",
        draft_id=draft.id,
        status=review.status,
        reviewed_by=review.reviewed_by,
    )
    return ContentDraftResponse.model_validate(draft)


@router.post("/drafts/{draft_id}/create-campaign")
async def create_campaign_from_draft(
    draft_id: int,
    db: DBSession,
    segment_id: int | None = Query(None, description="Target segment"),
):
    """Create a campaign from an approved email draft."""
    result = await db.execute(
        select(ContentDraft).where(ContentDraft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found",
        )

    if draft.content_type != "email":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only create campaigns from email drafts",
        )

    if draft.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Draft must be approved before creating a campaign",
        )

    from app.db.models import Campaign

    campaign = Campaign(
        name=f"Campaign: {draft.title}",
        subject=draft.subject or draft.title,
        html_content=draft.html_body or draft.body,
        plain_text_content=draft.body,
        segment_id=segment_id,
        is_ai_generated=True,
        ai_generation_prompt=draft.prompt_used,
    )
    db.add(campaign)

    draft.status = "published"
    draft.campaign_id = campaign.id

    await db.commit()
    await db.refresh(campaign)

    logger.info(
        "Campaign created from draft",
        draft_id=draft.id,
        campaign_id=campaign.id,
    )

    return {
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "draft_id": draft.id,
    }


@router.delete("/drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(draft_id: int, db: DBSession):
    """Delete a content draft."""
    result = await db.execute(
        select(ContentDraft).where(ContentDraft.id == draft_id)
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Draft {draft_id} not found",
        )

    await db.delete(draft)
    await db.commit()

    logger.info("Draft deleted", draft_id=draft_id)
