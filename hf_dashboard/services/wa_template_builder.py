"""Meta WhatsApp template component builder.

Single source of truth for turning a template spec into the Meta API
`components` payload. Used by both the CLI submitter
(`scripts/submit_wa_templates.py`) and the dashboard Template Studio
(`hf_dashboard/services/wa_sender.py::create_template`) so they cannot drift.

Input is a dict with these optional keys:
    header: {type: TEXT|IMAGE|VIDEO|DOCUMENT, text?, example?, url?}
    body:   {text, example?}
    footer: {text}
    buttons: [{type: URL|QUICK_REPLY|PHONE_NUMBER, text, url?, phone_number?}]

The reverse mapping (Meta components → flat WATemplate columns) lives in
`decompose_components` below — co-located so forward and inverse cannot
drift. Phase 7.4 added it so `WhatsAppSender.sync_templates_from_meta`
can populate body_text / header_text / etc. on every sync.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def build_components(template: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a template spec dict to Meta API components format."""
    components: list[dict[str, Any]] = []

    if "header" in template and template["header"]:
        h = template["header"]
        fmt = (h.get("type") or "TEXT").upper()
        comp: dict[str, Any] = {"type": "HEADER", "format": fmt}
        if fmt == "TEXT":
            comp["text"] = h["text"]
            if "example" in h:
                comp["example"] = {"header_text": h["example"]}
        elif fmt in ("IMAGE", "VIDEO", "DOCUMENT") and h.get("url"):
            comp["example"] = {"header_handle": [h["url"]]}
        components.append(comp)

    if "body" in template and template["body"]:
        b = template["body"]
        comp = {"type": "BODY", "text": b["text"].strip()}
        if "example" in b and b["example"]:
            example_values = b["example"] if isinstance(b["example"], list) else [b["example"]]
            comp["example"] = {"body_text": [example_values]}
        components.append(comp)

    if "footer" in template and template["footer"]:
        components.append({"type": "FOOTER", "text": template["footer"]["text"]})

    if "buttons" in template and template["buttons"]:
        buttons: list[dict[str, Any]] = []
        for btn in template["buttons"]:
            btype = btn["type"].upper()
            if btype == "URL":
                buttons.append({"type": "URL", "text": btn["text"], "url": btn["url"]})
            elif btype == "QUICK_REPLY":
                buttons.append({"type": "QUICK_REPLY", "text": btn["text"]})
            elif btype == "PHONE_NUMBER":
                buttons.append(
                    {"type": "PHONE_NUMBER", "text": btn["text"], "phone_number": btn["phone_number"]}
                )
            elif btype == "CATALOG":
                buttons.append({"type": "CATALOG", "text": btn["text"]})
        if buttons:
            components.append({"type": "BUTTONS", "buttons": buttons})

    return components


def decompose_components(components: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Inverse of `build_components` — Meta components shape → flat fields.

    Returns a dict with the keys WATemplate stores as flat columns:
        body_text:        str          (empty string if no BODY)
        header_format:    str | None   ("TEXT" | "IMAGE" | "VIDEO" | "DOCUMENT")
        header_text:      str | None   (only set when format == TEXT)
        header_asset_url: str | None   (only set for media headers)
        footer_text:      str | None
        buttons:          list[dict]   (empty list if no BUTTONS component)

    Designed to be safe to call on whatever Meta returns from the
    Graph API `/{waba_id}/message_templates` endpoint:

      - Components missing `type` are skipped.
      - Multiple HEADER or BODY entries (Meta should never return this)
        take the first; subsequent ones are logged and ignored.
      - Buttons with unknown `type` are preserved verbatim so future
        button kinds don't get silently dropped.
      - Header IMAGE/VIDEO/DOCUMENT URLs come from
        `example.header_handle[0]`. These are short-lived Meta CDN
        handles — fine for preview persistence but the actual send
        re-uploads media at send time.
    """
    out: dict[str, Any] = {
        "body_text": "",
        "header_format": None,
        "header_text": None,
        "header_asset_url": None,
        "footer_text": None,
        "buttons": [],
    }
    if not components:
        return out

    seen_header = False
    seen_body = False

    for comp in components:
        if not isinstance(comp, dict):
            continue
        ctype = comp.get("type")
        if not isinstance(ctype, str):
            continue
        ctype = ctype.upper()

        if ctype == "HEADER":
            if seen_header:
                log.warning("decompose_components: duplicate HEADER component, ignoring")
                continue
            seen_header = True
            fmt = (comp.get("format") or "TEXT").upper()
            out["header_format"] = fmt
            if fmt == "TEXT":
                out["header_text"] = comp.get("text") or ""
            elif fmt in ("IMAGE", "VIDEO", "DOCUMENT"):
                example = comp.get("example") or {}
                handles = example.get("header_handle") or []
                if isinstance(handles, list) and handles:
                    first = handles[0]
                    out["header_asset_url"] = first if isinstance(first, str) else ""
                else:
                    out["header_asset_url"] = ""

        elif ctype == "BODY":
            if seen_body:
                log.warning("decompose_components: duplicate BODY component, ignoring")
                continue
            seen_body = True
            out["body_text"] = comp.get("text") or ""

        elif ctype == "FOOTER":
            out["footer_text"] = comp.get("text") or ""

        elif ctype == "BUTTONS":
            buttons = comp.get("buttons")
            if isinstance(buttons, list):
                out["buttons"] = [b for b in buttons if isinstance(b, dict)]

        else:
            log.info("decompose_components: skipping unsupported component type %r", ctype)

    return out
