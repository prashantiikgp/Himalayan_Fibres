"""Email template management endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.core.logging import get_logger
from app.db.models import EmailTemplate, EmailType

router = APIRouter(prefix="/templates", tags=["templates"])
logger = get_logger(__name__)


# ===========================================
# SCHEMAS
# ===========================================


class TemplateCreate(BaseModel):
    """Schema for creating a template."""

    name: str
    slug: str
    description: str | None = None
    subject_template: str
    html_content: str
    plain_text_content: str | None = None
    email_type: EmailType
    required_variables: list[str] = []
    category: str | None = None
    is_cloudflare_import: bool = False


class TemplateUpdate(BaseModel):
    """Schema for updating a template."""

    name: str | None = None
    description: str | None = None
    subject_template: str | None = None
    html_content: str | None = None
    plain_text_content: str | None = None
    required_variables: list[str] | None = None
    category: str | None = None
    is_active: bool | None = None


class TemplateResponse(BaseModel):
    """Schema for template response."""

    id: int
    name: str
    slug: str
    description: str | None
    subject_template: str
    html_content: str
    plain_text_content: str | None
    email_type: EmailType
    required_variables: list[str]
    category: str | None
    is_cloudflare_import: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TemplateListResponse(BaseModel):
    """Schema for paginated template list."""

    templates: list[TemplateResponse]
    total: int


class TemplatePreviewRequest(BaseModel):
    """Schema for template preview request."""

    variables: dict[str, Any] = {}


class TemplatePreviewResponse(BaseModel):
    """Schema for template preview response."""

    subject: str
    html_content: str
    plain_text_content: str | None
    missing_variables: list[str]


# ===========================================
# ENDPOINTS
# ===========================================


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    db: DBSession,
    email_type: EmailType | None = None,
    category: str | None = None,
    is_active: bool | None = True,
    search: str | None = None,
):
    """List email templates with filtering."""
    query = select(EmailTemplate)

    if email_type:
        query = query.where(EmailTemplate.email_type == email_type)
    if category:
        query = query.where(EmailTemplate.category == category)
    if is_active is not None:
        query = query.where(EmailTemplate.is_active == is_active)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            (EmailTemplate.name.ilike(search_term))
            | (EmailTemplate.slug.ilike(search_term))
            | (EmailTemplate.description.ilike(search_term))
        )

    query = query.order_by(EmailTemplate.category, EmailTemplate.name)

    result = await db.execute(query)
    templates = result.scalars().all()

    return TemplateListResponse(
        templates=[TemplateResponse.model_validate(t) for t in templates],
        total=len(templates),
    )


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(template_data: TemplateCreate, db: DBSession):
    """Create a new email template."""
    # Check for existing slug
    result = await db.execute(
        select(EmailTemplate).where(EmailTemplate.slug == template_data.slug)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template with slug '{template_data.slug}' already exists",
        )

    template = EmailTemplate(**template_data.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)

    logger.info("Template created", name=template.name, slug=template.slug)
    return TemplateResponse.model_validate(template)


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: int, db: DBSession):
    """Get a specific template by ID."""
    result = await db.execute(
        select(EmailTemplate).where(EmailTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        )

    return TemplateResponse.model_validate(template)


@router.get("/slug/{slug}", response_model=TemplateResponse)
async def get_template_by_slug(slug: str, db: DBSession):
    """Get a specific template by slug."""
    result = await db.execute(
        select(EmailTemplate).where(EmailTemplate.slug == slug)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with slug '{slug}' not found",
        )

    return TemplateResponse.model_validate(template)


@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int, template_data: TemplateUpdate, db: DBSession
):
    """Update a template."""
    result = await db.execute(
        select(EmailTemplate).where(EmailTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        )

    update_data = template_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)

    logger.info("Template updated", name=template.name, slug=template.slug)
    return TemplateResponse.model_validate(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(template_id: int, db: DBSession):
    """Delete a template."""
    result = await db.execute(
        select(EmailTemplate).where(EmailTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        )

    await db.delete(template)
    await db.commit()

    logger.info("Template deleted", id=template_id)


@router.post("/{template_id}/preview", response_model=TemplatePreviewResponse)
async def preview_template(
    template_id: int,
    preview_data: TemplatePreviewRequest,
    db: DBSession,
):
    """Preview a rendered template with sample variables."""
    result = await db.execute(
        select(EmailTemplate).where(EmailTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template {template_id} not found",
        )

    from app.services.email_renderer import EmailRenderer

    renderer = EmailRenderer()

    # Provide defaults for missing variables
    variables = {
        "first_name": "John",
        "last_name": "Doe",
        "company": "Sample Company",
        "order_id": "ORD-12345",
        "order_total": "$150.00",
        "unsubscribe_url": "https://example.com/unsubscribe",
        **preview_data.variables,
    }

    # Find missing required variables
    missing = [v for v in template.required_variables if v not in variables]

    # Render template
    rendered_subject = renderer.render_string(template.subject_template, variables)
    rendered_html = renderer.render_string(template.html_content, variables)
    rendered_plain = (
        renderer.render_string(template.plain_text_content, variables)
        if template.plain_text_content
        else None
    )

    return TemplatePreviewResponse(
        subject=rendered_subject,
        html_content=rendered_html,
        plain_text_content=rendered_plain,
        missing_variables=missing,
    )


@router.post("/import/html")
async def import_html_template(
    db: DBSession,
    name: str = Query(..., description="Template name"),
    slug: str = Query(..., description="Template slug (unique identifier)"),
    email_type: EmailType = Query(..., description="Type of email"),
    subject_template: str = Query(..., description="Subject line (can include {{variables}})"),
    html_content: str = Query(..., description="HTML content from CloudHQ"),
    category: str | None = Query(None, description="Category (transactional, nurture, etc.)"),
):
    """
    Import an HTML template (e.g., from CloudHQ export).

    Pass the raw HTML content and metadata.
    """
    # Check for existing slug
    result = await db.execute(
        select(EmailTemplate).where(EmailTemplate.slug == slug)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template with slug '{slug}' already exists",
        )

    # Extract variables from HTML (look for {{variable_name}} patterns)
    import re

    variable_pattern = r"\{\{(\w+)\}\}"
    found_vars = list(set(re.findall(variable_pattern, html_content)))
    found_vars.extend(list(set(re.findall(variable_pattern, subject_template))))

    template = EmailTemplate(
        name=name,
        slug=slug,
        subject_template=subject_template,
        html_content=html_content,
        email_type=email_type,
        required_variables=list(set(found_vars)),
        category=category,
        is_cloudflare_import=True,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    logger.info(
        "HTML template imported",
        name=template.name,
        slug=template.slug,
        variables=found_vars,
    )

    return TemplateResponse.model_validate(template)
