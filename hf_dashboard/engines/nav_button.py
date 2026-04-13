"""NavButton — reusable sidebar navigation button factory.

Creates gr.Button instances styled with nav-btn / nav-btn-active CSS classes.
"""

from __future__ import annotations

import gradio as gr

from engines.theme_schemas import NavItem

ACTIVE = ["nav-btn", "nav-btn-active"]
INACTIVE = ["nav-btn"]


def create_nav_button(item: NavItem, is_active: bool = False) -> gr.Button:
    """Create a navigation button from a NavItem config."""
    label = f"{item.icon}  {item.label}"
    classes = ACTIVE if is_active else INACTIVE

    return gr.Button(
        value=label,
        variant="secondary",
        size="lg",
        elem_classes=classes,
        min_width=180,
        scale=1,
    )
