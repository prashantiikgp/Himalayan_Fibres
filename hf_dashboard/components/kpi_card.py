"""KPI card builder — reads styles from config/theme/components.yml."""

from __future__ import annotations

from components.styles import kpi_card_style, kpi_value_style, kpi_label_style


def render_kpi_card(value: str, label: str, delta: str = "", color: str = "", subtitle: str = "") -> str:
    delta_html = ""
    if delta:
        d_color = "#22c55e" if delta.startswith("+") else "#ef4444" if delta.startswith("-") else "#94a3b8"
        delta_html = f'<div style="font-size:11px; color:{d_color}; margin-top:2px;">{delta}</div>'

    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<div style="font-size:10px; color:#64748b; margin-top:2px;">{subtitle}</div>'

    return (
        f'<div style="{kpi_card_style()}">'
        f'<div style="{kpi_value_style(color)}">{value}</div>'
        f'<div style="{kpi_label_style()}">{label}</div>'
        f'{delta_html}{subtitle_html}</div>'
    )


def render_kpi_row(cards: list[tuple]) -> str:
    htmls = []
    for card in cards:
        if len(card) >= 5:
            htmls.append(render_kpi_card(card[0], card[1], delta=card[2], color=card[3], subtitle=card[4]))
        elif len(card) == 4:
            htmls.append(render_kpi_card(card[0], card[1], delta=card[2], color=card[3]))
        else:
            htmls.append(render_kpi_card(card[0], card[1]))
    return f'<div style="display:flex; gap:10px; flex-wrap:wrap;">{"".join(htmls)}</div>'
