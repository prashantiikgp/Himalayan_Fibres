"""Navigation engine — sidebar + page visibility toggling for Gradio.

Builds the app layout: header → sidebar + content area.
Each page is a gr.Group that shows/hides on nav button click.
Ported from Hotel Agent frontend/engines/navigation_engine.py.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

import gradio as gr

from engines.nav_button import create_nav_button, ACTIVE, INACTIVE
from engines.theme_schemas import NavItem
from loader.config_loader import get_config_loader
from shared.theme import COLORS
from shared.theme_css import DASHBOARD_CSS

log = logging.getLogger(__name__)


class DashboardRenderContext:
    """Context passed to each page's build() function."""

    def __init__(self, page_id: str, dashboard_name: str = ""):
        self.page_id = page_id
        self.dashboard_name = dashboard_name


def _render_header(title: str, subtitle: str = "") -> str:
    """Render the top header bar HTML."""
    sub_html = f' <span style="font-size:12px; color:{COLORS.TEXT_MUTED}; font-weight:400;">{subtitle}</span>' if subtitle else ""
    return (
        f'<div style="display:flex; align-items:center; justify-content:space-between; '
        f'padding:10px 20px; background:rgba(15,23,42,.80); '
        f'border-bottom:1px solid rgba(255,255,255,.06);">'
        f'<h1 style="font-size:16px; font-weight:700; color:#e7eaf3; margin:0;">'
        f'{title}{sub_html}</h1>'
        f'<span style="font-size:11px; color:{COLORS.TEXT_MUTED};">Himalayan Fibers</span>'
        f'</div>'
    )


def _resolve_page_module(page_id: str) -> Any:
    """Import the page module and return its build function."""
    try:
        mod = importlib.import_module(f"pages.{page_id}")
        if hasattr(mod, "build"):
            return mod.build
    except ImportError:
        log.warning("Page module not found: pages.%s", page_id)
    return None


def build_app_with_sidebar(title: str = "Himalayan Fibers") -> gr.Blocks:
    """Build the full Gradio app with sidebar navigation.

    Returns a gr.Blocks instance ready for mounting on FastAPI.
    Theme + CSS are passed to mount_gradio_app in app.py — Gradio 6 ignores
    them when set on the Blocks instance directly.
    """
    loader = get_config_loader()
    sidebar_config = loader.load_sidebar()
    dashboard_config = loader.load_dashboard()

    nav_items = sidebar_config.sidebar.nav_items
    default_page = dashboard_config.dashboard.default_page
    subtitle = dashboard_config.dashboard.subtitle

    with gr.Blocks(title=title) as app:
        # -- Auth gate --
        from services.config import get_settings
        settings = get_settings()
        has_auth = bool(settings.app_password)

        if has_auth:
            with gr.Group(visible=True) as auth_group:
                gr.HTML(
                    f'<div style="text-align:center; padding:60px 20px;">'
                    f'<div style="font-size:24px; font-weight:700; color:{COLORS.TEXT}; margin-bottom:8px;">'
                    f'Himalayan Fibers Dashboard</div>'
                    f'<div style="color:{COLORS.TEXT_SUBTLE}; margin-bottom:24px;">Enter password to continue</div>'
                    f'</div>'
                )
                with gr.Row():
                    gr.Column(scale=1)
                    with gr.Column(scale=1):
                        password_input = gr.Textbox(label="Password", type="password", placeholder="Dashboard password")
                        login_btn = gr.Button("Login", variant="primary")
                        login_error = gr.HTML(value="")
                    gr.Column(scale=1)

        # -- Header removed (W02 April 2026) — top banner was eating vertical
        #    space on every page and serving no functional purpose. The
        #    dashboard_group wrapper stays so the auth gate still has
        #    something to toggle visible after login.
        dashboard_group = gr.Group(visible=not has_auth)

        # -- Main layout: sidebar + content --
        with gr.Row(elem_classes=["main-layout"], visible=not has_auth) as main_layout:

            # -- Sidebar --
            with gr.Column(scale=0, min_width=200, elem_classes=["nav-sidebar"]):
                nav_buttons: dict[str, gr.Button] = {}
                for i, item in enumerate(nav_items):
                    if item.separator_before:
                        gr.HTML('<div class="nav-separator"></div>')
                    is_active = item.id == default_page
                    nav_buttons[item.id] = create_nav_button(item, is_active=is_active)

            # -- Content area --
            with gr.Column(scale=5, elem_classes=["content-area"]):
                page_groups: dict[str, gr.Group] = {}
                page_wirings: dict[str, dict] = {}

                for item in nav_items:
                    is_default = item.id == default_page
                    with gr.Group(visible=is_default) as grp:
                        ctx = DashboardRenderContext(
                            page_id=item.id,
                            dashboard_name=title,
                        )
                        builder = _resolve_page_module(item.id)
                        if builder:
                            result = builder(ctx)
                            if isinstance(result, dict) and "update_fn" in result:
                                page_wirings[item.id] = result
                        else:
                            gr.HTML(
                                f'<div style="text-align:center; padding:40px; color:{COLORS.TEXT_MUTED};">'
                                f'<div style="font-size:24px; margin-bottom:8px;">&#x1F6A7;</div>'
                                f'<div>Page "{item.label}" coming soon</div></div>'
                            )
                    page_groups[item.id] = grp

        # -- Wire navigation buttons --
        display_pids = [item.id for item in nav_items]

        for target_pid in display_pids:
            target_wiring = page_wirings.get(target_pid)

            def _make_nav_handler(_tid=target_pid, _wiring=target_wiring):
                def handler():
                    vis = [gr.update(visible=(pid == _tid)) for pid in display_pids]
                    btns = [gr.update(elem_classes=ACTIVE if pid == _tid else INACTIVE) for pid in display_pids]

                    if _wiring and "update_fn" in _wiring:
                        try:
                            data = _wiring["update_fn"]()
                            if isinstance(data, tuple):
                                return (*vis, *btns, *data)
                            return (*vis, *btns, data)
                        except Exception:
                            log.exception("Error refreshing page %s", _tid)
                            n = len(_wiring.get("outputs", []))
                            return (*vis, *btns, *(gr.update() for _ in range(n)))

                    return (*vis, *btns)

                return handler

            ordered_groups = [page_groups[pid] for pid in display_pids]
            ordered_buttons = [nav_buttons[pid] for pid in display_pids]
            outputs = list(ordered_groups) + list(ordered_buttons)

            if target_wiring:
                outputs += target_wiring.get("outputs", [])

            nav_buttons[target_pid].click(
                fn=_make_nav_handler(),
                inputs=[],
                outputs=outputs,
            )

        # -- Wire auth gate --
        if has_auth:
            def _login(password):
                if password == settings.app_password:
                    return (
                        gr.update(visible=False),  # auth_group
                        gr.update(visible=True),   # dashboard_group
                        gr.update(visible=True),   # main_layout
                        "",                        # login_error
                    )
                return (
                    gr.update(),  # auth_group stays
                    gr.update(),  # dashboard_group stays
                    gr.update(),  # main_layout stays
                    f'<div style="color:{COLORS.ERROR}; text-align:center; margin-top:8px;">Incorrect password</div>',
                )

            login_btn.click(
                fn=_login,
                inputs=[password_input],
                outputs=[auth_group, dashboard_group, main_layout, login_error],
            )

        # -- Auto-load default page data on startup --
        if default_page in page_wirings:
            home_wiring = page_wirings[default_page]
            try:
                app.load(fn=home_wiring["update_fn"], outputs=home_wiring["outputs"])
                log.info("Auto-load wired for default page: %s", default_page)
            except Exception:
                log.warning("Could not wire auto-load for %s", default_page)

    return app
