"""Styled HTML table builder — rich tables with colored cells, badges, progress bars."""

from __future__ import annotations

from shared.theme import COLORS, FONTS, SPACING
from components import styles


def render_table(
    headers: list[tuple[str, str]],
    rows: list[list[str]],
    title: str = "",
    subtitle: str = "",
) -> str:
    """Render a fully styled HTML table.

    Args:
        headers: List of (label, align) tuples.
        rows: List of row lists, where each cell is a pre-built HTML string
              (use cell(), cell_badge(), etc.).
        title: Optional title above the table.
        subtitle: Optional muted subtitle next to the title.
    """
    title_html = ""
    if title:
        sub = f' <span style="{styles.muted_caption()}">{subtitle}</span>' if subtitle else ""
        title_html = (
            f'<div style="margin-bottom:6px;">'
            f'<span style="font-size:{FONTS.MD}; font-weight:600; color:{COLORS.TEXT};">{title}</span>'
            f'{sub}</div>'
        )

    thead_cells = []
    for label, align in headers:
        thead_cells.append(
            f'<th style="{styles.table_header_cell(align)}">{label}</th>'
        )

    tbody_rows = []
    for row_cells in rows:
        tbody_rows.append(f'<tr style="{styles.table_body_row()}">{"".join(row_cells)}</tr>')

    return (
        f'{title_html}'
        f'<div style="overflow-x:auto; border-radius:{COLORS.CARD_BG}; '
        f'border:1px solid {COLORS.BORDER}; border-radius:8px;">'
        f'<table style="{styles.table_container()}">'
        f'<thead><tr style="{styles.table_header_row()}">{"".join(thead_cells)}</tr></thead>'
        f'<tbody>{"".join(tbody_rows)}</tbody>'
        f'</table></div>'
    )


# -- Cell builders --

def cell(text: str, align: str = "left", color: str = "", mono: bool = False, bold: bool = False) -> str:
    return f'<td style="{styles.table_body_cell(align=align, color=color, mono=mono, bold=bold)}">{text}</td>'


def cell_badge(text: str, bg: str, fg: str = "#fff") -> str:
    badge = f'<span style="{styles.badge_pill(bg, fg)}">{text}</span>'
    return f'<td style="padding:{SPACING.CELL_SM}; text-align:center;">{badge}</td>'


def cell_status(text: str, status: str) -> str:
    icon_map = {"sent": "&#x2705;", "failed": "&#x274C;", "draft": "&#x270F;",
                "pending": "&#x23F3;", "active": "&#x1F7E2;", "opted_in": "&#x2705;",
                "opted_out": "&#x274C;", "completed": "&#x2705;"}
    color_map = {"sent": COLORS.SUCCESS, "failed": COLORS.ERROR, "draft": COLORS.TEXT_MUTED,
                 "pending": COLORS.WARNING, "active": COLORS.SUCCESS, "opted_in": COLORS.SUCCESS,
                 "opted_out": COLORS.ERROR, "completed": COLORS.SUCCESS}
    icon = icon_map.get(status, "")
    color = color_map.get(status, COLORS.TEXT_SUBTLE)
    return f'<td style="{styles.table_body_cell(color=color)}">{icon} {text}</td>'
