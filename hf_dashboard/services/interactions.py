"""Contact interaction logging + retrieval.

Writes rows to `contact_interactions` so the Activity tab in the contact
edit drawer has something to show, and so every meaningful change to a
contact builds an audit trail over time.

Kinds (keep the list small and stable — the UI renders icons per kind):
    manual_edit       — user saved the edit drawer
    imported          — contact created via Add Contact or CSV import
    note_added        — threaded note appended via the Notes tab
    email_sent        — email delivery attempted (future: from broadcast engine)
    email_opened      — email open event (future)
    wa_sent           — WA message sent (future)
    wa_inbound        — WA message received (future)
    tag_added         — tag added via drawer (future, standalone event)
    segment_matched   — contact newly matched a segment (future)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from services.models import ContactInteraction

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Writer
# ══════════════════════════════════════════════════════════════════════

def log_interaction(
    db: Session,
    contact_id: str,
    kind: str,
    summary: str = "",
    payload: dict | None = None,
    actor: str = "user",
    commit: bool = True,
) -> ContactInteraction | None:
    """Append one row to contact_interactions.

    Never raises — logs and returns None on error. Interaction logging is a
    side effect of user actions; it should not break the primary write.
    """
    if not contact_id:
        return None
    try:
        row = ContactInteraction(
            contact_id=contact_id,
            kind=kind,
            summary=(summary or "")[:255],
            payload=payload or {},
            occurred_at=datetime.now(timezone.utc),
            actor=actor,
        )
        db.add(row)
        if commit:
            db.commit()
        return row
    except Exception as e:
        log.warning("log_interaction failed for %s/%s: %s", contact_id, kind, e)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def summarize_diff(before: dict, after: dict) -> str:
    """Render a short summary of what changed between two field dicts.

    Used by the drawer save path to generate a human-readable summary like
    "company, lifecycle, 2 tags" without writing a full diff.
    """
    changed: list[str] = []
    for k, new in after.items():
        old = before.get(k)
        if old == new:
            continue
        if k == "tags":
            a = set(old or [])
            b = set(new or [])
            added = len(b - a)
            removed = len(a - b)
            if added or removed:
                parts = []
                if added:
                    parts.append(f"+{added}")
                if removed:
                    parts.append(f"-{removed}")
                changed.append(f"tags({', '.join(parts)})")
        else:
            changed.append(k)
    if not changed:
        return "no-op save"
    return ", ".join(changed)


# ══════════════════════════════════════════════════════════════════════
# Reader — powers the Activity tab
# ══════════════════════════════════════════════════════════════════════

def get_interactions(db: Session, contact_id: str, limit: int = 50) -> list[ContactInteraction]:
    if not contact_id:
        return []
    return (
        db.query(ContactInteraction)
        .filter(ContactInteraction.contact_id == contact_id)
        .order_by(ContactInteraction.occurred_at.desc())
        .limit(limit)
        .all()
    )


# ══════════════════════════════════════════════════════════════════════
# UI helpers — icons + relative time formatting
# ══════════════════════════════════════════════════════════════════════

_KIND_ICON = {
    "manual_edit": "✎",
    "imported": "⬇",
    "note_added": "📝",
    "email_sent": "✉",
    "email_opened": "👁",
    "wa_sent": "💬",
    "wa_inbound": "⬅",
    "tag_added": "🏷",
    "segment_matched": "🎯",
}

_KIND_COLOR = {
    "manual_edit": "#6366f1",
    "imported": "#22c55e",
    "note_added": "#f59e0b",
    "email_sent": "#06b6d4",
    "email_opened": "#14b8a6",
    "wa_sent": "#22c55e",
    "wa_inbound": "#8b5cf6",
    "tag_added": "#ec4899",
    "segment_matched": "#ef4444",
}


def icon_for(kind: str) -> str:
    return _KIND_ICON.get(kind, "•")


def color_for(kind: str) -> str:
    return _KIND_COLOR.get(kind, "#94a3b8")


def relative_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        # SQLite-stored datetimes come back naive; assume UTC
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    if days < 30:
        return f"{days // 7}w ago"
    return dt.strftime("%Y-%m-%d")


def render_activity_html(interactions: Iterable[ContactInteraction]) -> str:
    """Render a list of interactions as a vertical timeline."""
    items = list(interactions)
    if not items:
        return (
            '<div style="color:#64748b; font-size:11px; font-style:italic; '
            'padding:16px; text-align:center;">No activity yet for this contact. '
            'Edits, added notes, and sends will appear here.</div>'
        )

    rows = []
    for it in items:
        icon = icon_for(it.kind)
        color = color_for(it.kind)
        kind_label = it.kind.replace("_", " ").title()
        summary = it.summary or ""
        when = relative_time(it.occurred_at)
        actor = it.actor or "system"
        rows.append(
            f'<div style="display:flex; gap:10px; padding:8px 0; '
            f'border-bottom:1px solid rgba(255,255,255,.05);">'
            f'<div style="flex:0 0 28px; height:28px; width:28px; border-radius:14px; '
            f'background:{color}22; border:1px solid {color}55; color:{color}; '
            f'display:flex; align-items:center; justify-content:center; font-size:13px;">'
            f'{icon}</div>'
            f'<div style="flex:1; min-width:0;">'
            f'<div style="font-size:11px; font-weight:600; color:#e7eaf3;">{kind_label}'
            f'<span style="font-weight:400; color:#64748b; margin-left:8px;">· {when}</span>'
            f'</div>'
            f'<div style="font-size:11px; color:#94a3b8; margin-top:2px; '
            f'overflow:hidden; text-overflow:ellipsis;">{summary or "—"}</div>'
            f'<div style="font-size:10px; color:#64748b; margin-top:1px;">{actor}</div>'
            f'</div></div>'
        )
    return f'<div style="max-height:320px; overflow-y:auto;">{"".join(rows)}</div>'


def render_notes_html(notes: Iterable, legacy_note: str = "") -> str:
    """Render a list of ContactNote rows + an optional legacy note blob."""
    items = list(notes)
    blocks = []
    for n in items:
        when = relative_time(n.created_at)
        author = n.author or "user"
        body_html = (n.body or "").replace("\n", "<br>")
        blocks.append(
            f'<div style="padding:10px 12px; margin-bottom:8px; '
            f'background:rgba(15,23,42,.55); border:1px solid rgba(255,255,255,.06); '
            f'border-radius:6px;">'
            f'<div style="font-size:10px; color:#64748b; margin-bottom:4px;">'
            f'{author} · {when}</div>'
            f'<div style="font-size:12px; color:#e2e8f0; line-height:1.5;">{body_html}</div>'
            f'</div>'
        )
    if legacy_note and legacy_note.strip():
        legacy_html = legacy_note.replace("\n", "<br>")
        blocks.append(
            f'<div style="padding:10px 12px; margin-top:8px; '
            f'background:rgba(99,102,241,.06); border:1px dashed rgba(99,102,241,.25); '
            f'border-radius:6px;">'
            f'<div style="font-size:10px; color:#94a3b8; margin-bottom:4px;">'
            f'Legacy note (from contacts.notes field)</div>'
            f'<div style="font-size:12px; color:#cbd5e1; line-height:1.5; font-style:italic;">'
            f'{legacy_html}</div>'
            f'</div>'
        )
    if not blocks:
        return (
            '<div style="color:#64748b; font-size:11px; font-style:italic; '
            'padding:16px; text-align:center;">No notes yet. '
            'Add one below to start a thread.</div>'
        )
    return "".join(blocks)
