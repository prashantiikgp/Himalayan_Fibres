"""Segment rule evaluator + bulk helpers.

Extends the existing `broadcast_engine.get_segment_contacts` evaluator with
support for `tags`, `lifecycle`, `country`, and `consent_status` rule keys.
Rule shape is a flat dict `{field: [values]}`, ANDed across fields, matching
the format already used by `data/segments.csv` and seeded system segments.

Supported rule keys:
    customer_type      [str, ...]   equality on Contact.customer_type
    customer_subtype   [str, ...]   equality on Contact.customer_subtype
    geography          [str, ...]   equality on Contact.geography
    country            [str, ...]   equality on Contact.country
    lifecycle          [str, ...]   equality on Contact.lifecycle
    consent_status     [str, ...]   equality on Contact.consent_status
    tags               [str, ...]   contact must have ANY of these tags

Bulk helpers precompute {contact_id: [segment_ids]} so the contacts table
can render a Segments column without evaluating rules per row.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Iterable

from sqlalchemy.orm import Session

from services.models import Contact, Segment


# ══════════════════════════════════════════════════════════════════════
# Rule evaluation
# ══════════════════════════════════════════════════════════════════════

_SIMPLE_EQ_FIELDS = {
    "customer_type": Contact.customer_type,
    "customer_subtype": Contact.customer_subtype,
    "geography": Contact.geography,
    "country": Contact.country,
    "lifecycle": Contact.lifecycle,
    "consent_status": Contact.consent_status,
    "engagement_level": Contact.engagement_level,
}


def build_segment_query(db: Session, rules: dict | None):
    """Translate a rule dict into a SQLAlchemy query filtered to matches.

    Empty/None rules → all contacts.
    Tag matching happens in Python because SQLite JSON containment via
    SQLAlchemy is driver-specific; for ~1000 rows the cost is trivial.
    """
    q = db.query(Contact)
    if not rules:
        return q, None  # tag_filter = None

    for key, col in _SIMPLE_EQ_FIELDS.items():
        if key in rules and rules[key]:
            values = rules[key]
            if not isinstance(values, list):
                values = [values]
            q = q.filter(col.in_(values))

    tag_filter = None
    if "tags" in rules and rules["tags"]:
        wanted = set(rules["tags"])
        tag_filter = wanted

    return q, tag_filter


def evaluate_segment(db: Session, segment: Segment) -> list[Contact]:
    """Return all contacts matching a segment's rule."""
    q, tag_filter = build_segment_query(db, segment.rules or {})
    rows = q.all()
    if tag_filter:
        rows = [
            c for c in rows
            if c.tags and any(t in tag_filter for t in c.tags)
        ]
    return rows


def get_segment_member_ids(db: Session, segment: Segment) -> set[str]:
    """Return set of contact IDs matching a segment."""
    return {c.id for c in evaluate_segment(db, segment)}


def count_segment_members(db: Session, segment: Segment) -> int:
    return len(get_segment_member_ids(db, segment))


# ══════════════════════════════════════════════════════════════════════
# In-memory matcher — for checking a single contact against all segments
# without any DB round-trips. Used by the edit drawer so opening a row
# doesn't pull every contact from the pooler.
# ══════════════════════════════════════════════════════════════════════

def contact_matches_rule(contact, rules: dict | None) -> bool:
    """Evaluate a rule dict against an in-memory Contact object.

    Mirrors build_segment_query's semantics: flat dict of
    {field: [allowed values]}, AND across fields, with a tags rule
    matching if the contact has ANY of the listed tags.
    """
    if not rules:
        return True
    for field, col in _SIMPLE_EQ_FIELDS.items():
        allowed = rules.get(field)
        if not allowed:
            continue
        if not isinstance(allowed, list):
            allowed = [allowed]
        value = getattr(contact, field, None) or ""
        if value not in allowed:
            return False
    tag_filter = rules.get("tags")
    if tag_filter:
        if not isinstance(tag_filter, list):
            tag_filter = [tag_filter]
        wanted = set(tag_filter)
        ctags = contact.tags or []
        if not any(t in wanted for t in ctags):
            return False
    return True


def segments_for_contact(contact, segments: Iterable[Segment]) -> list[str]:
    """Return the ids of segments whose rules this contact matches. Pure Python."""
    out = []
    for seg in segments:
        if contact_matches_rule(contact, seg.rules or {}):
            out.append(seg.id)
    return out


# ══════════════════════════════════════════════════════════════════════
# Bulk helpers for the contacts table
# ══════════════════════════════════════════════════════════════════════

def get_contact_segments_map(
    db: Session,
    segments: Iterable[Segment] | None = None,
) -> dict[str, list[str]]:
    """Build `{contact_id: [segment_id, ...]}` for all active segments.

    One query per segment (not one per contact), so cost is O(segments)
    regardless of contact count. Re-run this on every render — no cache,
    because segments or contacts may have changed.
    """
    if segments is None:
        segments = db.query(Segment).filter(Segment.is_active == True).all()  # noqa: E712
    out: dict[str, list[str]] = {}
    for seg in segments:
        ids = get_segment_member_ids(db, seg)
        for cid in ids:
            out.setdefault(cid, []).append(seg.id)
    return out


def get_all_active_segments(db: Session) -> list[Segment]:
    return db.query(Segment).filter(Segment.is_active == True).order_by(Segment.name).all()  # noqa: E712


def get_segments_by_id(db: Session) -> dict[str, Segment]:
    return {s.id: s for s in db.query(Segment).all()}


# ══════════════════════════════════════════════════════════════════════
# Tag inventory
# ══════════════════════════════════════════════════════════════════════

def get_all_tags_from_contacts(db: Session) -> list[str]:
    """Return the sorted union of every tag ever set on any contact.

    Iterates contacts and unions the JSON list column. Predefined tags from
    `config/contacts/schema.yml` are seed values only — this function is the
    authoritative list of what tags actually exist in the data.
    """
    tags: set[str] = set()
    # Only select the tags column to keep the query small
    for (raw,) in db.query(Contact.tags).all():
        if not raw:
            continue
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                continue
        if isinstance(raw, list):
            for t in raw:
                if t and isinstance(t, str):
                    tags.add(t.strip())
    return sorted(tags)


# ══════════════════════════════════════════════════════════════════════
# Segment color helper — stable per-id color for pills
# ══════════════════════════════════════════════════════════════════════

_SEGMENT_COLOR_PALETTE = [
    "#6366f1",  # indigo
    "#22c55e",  # green
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#14b8a6",  # teal
    "#ec4899",  # pink
    "#8b5cf6",  # violet
    "#06b6d4",  # cyan
    "#84cc16",  # lime
    "#f97316",  # orange
]


@lru_cache(maxsize=128)
def segment_color(segment_id: str) -> str:
    """Stable color per segment id, cycling through the palette."""
    if not segment_id:
        return "#64748b"
    h = abs(hash(segment_id)) % len(_SEGMENT_COLOR_PALETTE)
    return _SEGMENT_COLOR_PALETTE[h]
