"""Contact segmentation service."""

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Contact, ConsentStatus, ContactType, Segment

logger = get_logger(__name__)


def build_segment_query(rules: dict[str, Any]):
    """
    Build a SQLAlchemy query from segment rules.

    Rules structure:
    {
        "contact_types": ["carpet_exporter", "handicraft_exporter"],
        "countries": ["India", "Nepal"],
        "tags": ["premium"],
        "consent_statuses": ["opted_in"],
        "has_opened_email": true,
        "has_clicked_email": false,
        "min_emails_sent": 1,
        "max_emails_sent": 10
    }

    All rules are combined with AND logic.
    Multiple values within a rule are combined with OR logic.
    """
    query = select(Contact)
    conditions = []

    # Contact types (OR within rule)
    if "contact_types" in rules and rules["contact_types"]:
        type_values = [
            ContactType(t) if isinstance(t, str) else t
            for t in rules["contact_types"]
        ]
        conditions.append(Contact.contact_type.in_(type_values))

    # Countries (OR within rule)
    if "countries" in rules and rules["countries"]:
        conditions.append(Contact.country.in_(rules["countries"]))

    # Tags (any of the tags)
    if "tags" in rules and rules["tags"]:
        # JSONB array contains any of the specified tags
        tag_conditions = [
            Contact.tags.contains([tag]) for tag in rules["tags"]
        ]
        conditions.append(or_(*tag_conditions))

    # Consent statuses (OR within rule)
    if "consent_statuses" in rules and rules["consent_statuses"]:
        status_values = [
            ConsentStatus(s) if isinstance(s, str) else s
            for s in rules["consent_statuses"]
        ]
        conditions.append(Contact.consent_status.in_(status_values))

    # Has opened email
    if "has_opened_email" in rules:
        if rules["has_opened_email"]:
            conditions.append(Contact.total_emails_opened > 0)
        else:
            conditions.append(Contact.total_emails_opened == 0)

    # Has clicked email
    if "has_clicked_email" in rules:
        if rules["has_clicked_email"]:
            conditions.append(Contact.total_emails_clicked > 0)
        else:
            conditions.append(Contact.total_emails_clicked == 0)

    # Min emails sent
    if "min_emails_sent" in rules and rules["min_emails_sent"] is not None:
        conditions.append(Contact.total_emails_sent >= rules["min_emails_sent"])

    # Max emails sent
    if "max_emails_sent" in rules and rules["max_emails_sent"] is not None:
        conditions.append(Contact.total_emails_sent <= rules["max_emails_sent"])

    # Apply all conditions with AND
    if conditions:
        query = query.where(and_(*conditions))

    return query


async def get_segment_contacts(
    db: AsyncSession,
    segment_id: int,
    limit: int | None = None,
) -> list[Contact]:
    """
    Get contacts matching a segment's rules.

    Args:
        db: Database session
        segment_id: Segment ID
        limit: Maximum number of contacts to return

    Returns:
        List of matching contacts
    """
    # Get segment
    result = await db.execute(select(Segment).where(Segment.id == segment_id))
    segment = result.scalar_one_or_none()

    if not segment:
        return []

    # Build and execute query
    query = build_segment_query(segment.rules)

    if limit:
        query = query.limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def evaluate_contact_segments(
    db: AsyncSession,
    contact_id: int,
) -> list[Segment]:
    """
    Find all segments a contact belongs to.

    Args:
        db: Database session
        contact_id: Contact ID

    Returns:
        List of segments the contact matches
    """
    # Get contact
    contact_result = await db.execute(
        select(Contact).where(Contact.id == contact_id)
    )
    contact = contact_result.scalar_one_or_none()

    if not contact:
        return []

    # Get all active segments
    segments_result = await db.execute(
        select(Segment).where(Segment.is_active == True)
    )
    segments = segments_result.scalars().all()

    matching_segments = []

    for segment in segments:
        # Build query for this segment
        query = build_segment_query(segment.rules).where(Contact.id == contact_id)

        # Check if contact matches
        result = await db.execute(query)
        if result.scalar_one_or_none():
            matching_segments.append(segment)

    return matching_segments


def get_segment_description(rules: dict[str, Any]) -> str:
    """
    Generate a human-readable description of segment rules.

    Args:
        rules: Segment rules dict

    Returns:
        Human-readable description
    """
    parts = []

    if "contact_types" in rules and rules["contact_types"]:
        types = ", ".join(rules["contact_types"])
        parts.append(f"Contact type is {types}")

    if "countries" in rules and rules["countries"]:
        countries = ", ".join(rules["countries"])
        parts.append(f"Country is {countries}")

    if "tags" in rules and rules["tags"]:
        tags = ", ".join(rules["tags"])
        parts.append(f"Has tags: {tags}")

    if "consent_statuses" in rules and rules["consent_statuses"]:
        statuses = ", ".join(rules["consent_statuses"])
        parts.append(f"Consent status is {statuses}")

    if rules.get("has_opened_email"):
        parts.append("Has opened at least one email")
    elif rules.get("has_opened_email") is False:
        parts.append("Has not opened any emails")

    if rules.get("has_clicked_email"):
        parts.append("Has clicked at least one email")
    elif rules.get("has_clicked_email") is False:
        parts.append("Has not clicked any emails")

    if "min_emails_sent" in rules and rules["min_emails_sent"]:
        parts.append(f"Received at least {rules['min_emails_sent']} emails")

    if "max_emails_sent" in rules and rules["max_emails_sent"]:
        parts.append(f"Received at most {rules['max_emails_sent']} emails")

    if not parts:
        return "All contacts"

    return " AND ".join(parts)
