"""Contacts endpoints — Phase 1 list/filter/segments.

This commit ships the read-side: GET /contacts (paginated, filterable),
GET /contacts/tags, GET /contacts/countries, GET /segments.

Edit + import + drawer detail land in a follow-up commit.

Implementation reuses hf_dashboard/services/segments.py helpers — no
duplicated business logic. The "segments matched" column is computed
in Python for the current page only (same trick v1 uses; ~0ms for
50 rows × ~10 segments).
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_

from api_v2.deps import require_auth
from api_v2.schemas.contacts import (
    ContactListResponse,
    ContactRow,
    CountriesResponse,
    SegmentSummary,
    SegmentsResponse,
    TagsResponse,
)

# Reused v1 services — single source for segment rules + caching.
from services.database import get_db  # type: ignore[import-not-found]
from services.models import Contact  # type: ignore[import-not-found]
from services.segments import (  # type: ignore[import-not-found]
    count_segment_members,
    get_active_segments_cached,
    get_all_tags_from_contacts,
    segments_for_contact,
)

router = APIRouter()


def _is_real_email(email: str | None) -> bool:
    if not email:
        return False
    if "@placeholder.local" in email or email.startswith("wa_"):
        return False
    return True


@router.get("/contacts", response_model=ContactListResponse)
async def list_contacts(
    _auth: Annotated[None, Depends(require_auth)],
    segment: str | None = Query(None, description="Filter by customer_type segment id"),
    lifecycle: str | None = Query(None, description="Filter by lifecycle stage id"),
    country: str | None = Query(None),
    channel: Literal["all", "email", "whatsapp", "both"] = "all",
    tags: list[str] = Query(default_factory=list),
    search: str = "",
    page: int = Query(0, ge=0),
    page_size: int = Query(50, ge=1, le=200),
) -> ContactListResponse:
    db = get_db()
    try:
        # Plan D Phase 1.3 — select only the 14 columns the row renderer +
        # rule engine touch, not the full ~38 column Contact row.
        q = db.query(Contact).with_entities(
            Contact.id,
            Contact.first_name,
            Contact.last_name,
            Contact.company,
            Contact.email,
            Contact.phone,
            Contact.wa_id,
            Contact.lifecycle,
            Contact.customer_type,
            Contact.consent_status,
            Contact.country,
            Contact.tags,
            Contact.customer_subtype,
            Contact.geography,
        )

        if segment and segment != "all":
            q = q.filter(Contact.customer_type == segment)
        if lifecycle and lifecycle != "all":
            q = q.filter(Contact.lifecycle == lifecycle)
        if country and country != "all":
            q = q.filter(Contact.country == country)
        if channel == "email":
            q = q.filter(Contact.email.isnot(None), ~Contact.email.like("%placeholder%"))
        elif channel == "whatsapp":
            q = q.filter(Contact.wa_id.isnot(None))
        elif channel == "both":
            q = q.filter(
                Contact.email.isnot(None),
                ~Contact.email.like("%placeholder%"),
                Contact.wa_id.isnot(None),
            )
        if search:
            term = f"%{search}%"
            q = q.filter(
                or_(
                    Contact.email.ilike(term),
                    Contact.first_name.ilike(term),
                    Contact.last_name.ilike(term),
                    Contact.company.ilike(term),
                )
            )

        # Tag filter — JSON columns evaluated in Python (SQLite + Postgres compat).
        tag_set = {t.strip() for t in tags if t and t.strip()} or None
        if tag_set:
            id_subset: set[str] = set()
            for cid, ctags in db.query(Contact.id, Contact.tags).all():
                ctags_list = ctags or []
                if any(t in tag_set for t in ctags_list):
                    id_subset.add(cid)
            if not id_subset:
                return ContactListResponse(
                    contacts=[], total=0, page=0, page_size=page_size, total_pages=1
                )
            q = q.filter(Contact.id.in_(id_subset))

        total = q.count()
        total_pages = max(1, (total + page_size - 1) // page_size)
        if page >= total_pages:
            page = max(total_pages - 1, 0)

        rows = q.order_by(Contact.company, Contact.first_name).offset(page * page_size).limit(page_size).all()

        # Segment-rule eval for the page only — cached segments list (5min TTL).
        all_segments = get_active_segments_cached()
        contacts_out: list[ContactRow] = []
        for r in rows:
            seg_ids = segments_for_contact(r, all_segments)
            channels: list[Literal["email", "whatsapp"]] = []
            if _is_real_email(r.email):
                channels.append("email")
            if r.wa_id:
                channels.append("whatsapp")
            contacts_out.append(
                ContactRow(
                    id=r.id,
                    first_name=r.first_name or "",
                    last_name=r.last_name or "",
                    company=r.company or "",
                    email=r.email if _is_real_email(r.email) else "",
                    phone=r.phone or "",
                    wa_id=r.wa_id,
                    lifecycle=r.lifecycle or "",
                    customer_type=r.customer_type or "",
                    consent_status=r.consent_status or "",
                    country=r.country or "",
                    tags=list(r.tags or []),
                    segments=seg_ids,
                    channels=channels,
                )
            )

        return ContactListResponse(
            contacts=contacts_out,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    finally:
        db.close()


@router.get("/contacts/tags", response_model=TagsResponse)
async def list_contact_tags(_auth: Annotated[None, Depends(require_auth)]) -> TagsResponse:
    db = get_db()
    try:
        return TagsResponse(tags=get_all_tags_from_contacts(db))
    finally:
        db.close()


@router.get("/contacts/countries", response_model=CountriesResponse)
async def list_contact_countries(
    _auth: Annotated[None, Depends(require_auth)],
) -> CountriesResponse:
    db = get_db()
    try:
        rows = (
            db.query(Contact.country)
            .filter(Contact.country.isnot(None), Contact.country != "")
            .distinct()
            .order_by(Contact.country)
            .all()
        )
        return CountriesResponse(countries=[r[0] for r in rows if r[0]])
    finally:
        db.close()


@router.get("/segments", response_model=SegmentsResponse)
async def list_segments(_auth: Annotated[None, Depends(require_auth)]) -> SegmentsResponse:
    db = get_db()
    try:
        segments = get_active_segments_cached()
        out = [
            SegmentSummary(
                id=s.id,
                name=s.name,
                color=getattr(s, "color", None),
                description=getattr(s, "description", None),
                member_count=count_segment_members(db, s),
            )
            for s in segments
        ]
        return SegmentsResponse(segments=out)
    finally:
        db.close()
