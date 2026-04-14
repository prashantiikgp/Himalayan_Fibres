"""Shared SQLAlchemy column-tuple constants for egress-trimmed queries.

These live in Python rather than YAML for one simple reason: they're
references to `Column` objects, not strings. A YAML file would have
to hold column NAMES which we'd resolve to `Column` objects in code,
which means typos only surface at runtime. Keeping them as Python
references means a renamed column triggers an ImportError at startup.

If you're looking for tunable constants that should be YAML-driven,
see `config/cache/ttl.yml` + `engines/cache_schemas.py`.

Usage:
    from services.query_helpers import CONTACT_LIST_COLS

    q = db.query(Contact).with_entities(*CONTACT_LIST_COLS)
    rows = q.filter(...).all()

Every tuple below represents the minimum set of columns a specific
renderer or export needs. Adding a new caller? Create a new tuple.
Do NOT extend an existing one to cover more fields — the whole point
is that narrow tuples = narrow egress.
"""

from __future__ import annotations

from services.models import Contact, WAChat, WAMessage

# pages/contacts.py :: _build_table — table row renderer uses name
# (first+last+company), channels (email+wa_id), lifecycle, tags,
# city, country, plus segment rule matcher fields (customer_type,
# customer_subtype, geography, consent_status). 15 cols of 38.
CONTACT_LIST_COLS = (
    Contact.id,
    Contact.first_name,
    Contact.last_name,
    Contact.company,
    Contact.email,
    Contact.phone,
    Contact.wa_id,
    Contact.lifecycle,
    Contact.tags,
    Contact.city,
    Contact.country,
    Contact.customer_type,
    Contact.customer_subtype,
    Contact.geography,
    Contact.consent_status,
)

# pages/contacts.py :: _download — CSV export. 9 cols.
CONTACT_CSV_COLS = (
    Contact.email,
    Contact.first_name,
    Contact.last_name,
    Contact.company,
    Contact.phone,
    Contact.country,
    Contact.lifecycle,
    Contact.consent_status,
    Contact.wa_id,
)

# pages/wa_inbox.py :: _get_active_conversations — conv list item renderer.
# Join key + Contact identity columns + WAChat preview columns. 7 cols.
WA_CONV_LIST_COLS = (
    Contact.id,
    Contact.first_name,
    Contact.last_name,
    Contact.company,
    WAChat.last_message_at,
    WAChat.last_message_preview,
    WAChat.unread_count,
)

# pages/home.py :: recent activity feed — uses text-preview + direction
# + created_at for the merged Email/WA list.
ACTIVITY_EMAIL_COLS = ...  # filled in when we wire the Home feed
ACTIVITY_WA_COLS = ...     # filled in when we wire the Home feed
