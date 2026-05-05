"""/api/v2/email/templates — Email Template CRUD (Phase 6.4).

Email templates have no Meta-style immutability — they're plain
HTML+subject blobs the SMTP sender renders against per-recipient
variables. Save is in-place; no clone-on-edit. Delete works on any
template (no equivalent of WA's submitted/approved restriction).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from api_v2.deps import require_auth
from api_v2.schemas.email_send import EmailVariableSpec
from api_v2.schemas.email_templates import (
    EmailTemplateOut,
    EmailTemplatesResponse,
    EmailTemplateUpsert,
)

from services.database import get_db  # type: ignore[import-not-found]
from services.models import EmailTemplate  # type: ignore[import-not-found]
from services.template_seed import get_template_meta  # type: ignore[import-not-found]


router = APIRouter(tags=["email_templates"], dependencies=[Depends(require_auth)])


def _resolve_variable_spec(t: EmailTemplate) -> list[EmailVariableSpec]:
    """Lift per-variable metadata from the template's `.meta.yml`.

    For DB-only templates (no YAML companion file) we synthesize a
    minimal text-input spec from `required_variables` so the Studio
    + Compose UI still renders typed inputs.
    """
    meta = get_template_meta(t.slug or "")
    if meta and meta.variables:
        return [
            EmailVariableSpec(
                name=v.name,
                label=v.label or "",
                type=v.type or "text",  # type: ignore[arg-type]
                placeholder=v.placeholder or "",
                example=v.example or "",
                required=bool(v.required),
            )
            for v in meta.variables
        ]

    required = set(meta.required_variables) if meta else set()
    fallback: list[EmailVariableSpec] = []
    for name in list(t.required_variables or []):
        fallback.append(
            EmailVariableSpec(
                name=name,
                label=name.replace("_", " ").title(),
                type="text",
                placeholder="",
                example="",
                required=name in required or True,
            )
        )
    return fallback


def _to_out(t: EmailTemplate) -> EmailTemplateOut:
    return EmailTemplateOut(
        id=t.id,
        name=t.name,
        slug=t.slug,
        subject_template=t.subject_template or "",
        html_content=t.html_content or "",
        email_type=t.email_type or "campaign",
        required_variables=list(t.required_variables or []),
        category=t.category or "",
        is_active=bool(t.is_active),
        created_at=t.created_at,
        variable_spec=_resolve_variable_spec(t),
    )


def _apply(t: EmailTemplate, body: EmailTemplateUpsert) -> None:
    if body.name is not None:
        t.name = body.name
    t.subject_template = body.subject_template or ""
    t.html_content = body.html_content or ""
    t.email_type = body.email_type or "campaign"
    t.required_variables = list(body.required_variables or [])
    t.category = body.category or ""
    t.is_active = bool(body.is_active)


@router.get("/email/templates", response_model=EmailTemplatesResponse)
def list_email_templates(
    active_only: Annotated[bool, Query()] = False,
    email_type: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> EmailTemplatesResponse:
    db = get_db()
    try:
        q = db.query(EmailTemplate)
        if active_only:
            q = q.filter(EmailTemplate.is_active.is_(True))
        if email_type:
            q = q.filter(EmailTemplate.email_type == email_type)
        if category:
            q = q.filter(EmailTemplate.category == category)
        if search:
            term = f"%{search}%"
            q = q.filter(EmailTemplate.name.ilike(term) | EmailTemplate.slug.ilike(term))
        rows = q.order_by(EmailTemplate.name.asc()).all()
        return EmailTemplatesResponse(
            templates=[_to_out(t) for t in rows],
            total=len(rows),
        )
    finally:
        db.close()


@router.get("/email/templates/{template_id}", response_model=EmailTemplateOut)
def get_email_template(template_id: int) -> EmailTemplateOut:
    db = get_db()
    try:
        t = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Email template not found")
        return _to_out(t)
    finally:
        db.close()


@router.post(
    "/email/templates",
    response_model=EmailTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_email_template(body: EmailTemplateUpsert) -> EmailTemplateOut:
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not (body.slug or "").strip():
        raise HTTPException(status_code=400, detail="slug is required")
    name = body.name.strip()
    slug = body.slug.strip()

    db = get_db()
    try:
        if db.query(EmailTemplate).filter(EmailTemplate.slug == slug).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email template slug {slug!r} already exists",
            )
        t = EmailTemplate(name=name, slug=slug)
        _apply(t, body)
        db.add(t)
        try:
            db.commit()
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=getattr(e.orig, "args", [str(e)])[0],
            ) from e
        db.refresh(t)
        return _to_out(t)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.post(
    "/email/templates/{template_id}/save", response_model=EmailTemplateOut
)
def save_email_template(
    template_id: int, body: EmailTemplateUpsert
) -> EmailTemplateOut:
    db = get_db()
    try:
        t = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Email template not found")
        _apply(t, body)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(t)
        return _to_out(t)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.delete(
    "/email/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_email_template(template_id: int) -> None:
    db = get_db()
    try:
        t = db.query(EmailTemplate).filter(EmailTemplate.id == template_id).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Email template not found")
        db.delete(t)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
