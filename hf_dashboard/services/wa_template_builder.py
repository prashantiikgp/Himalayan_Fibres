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
"""

from __future__ import annotations

from typing import Any


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
        if buttons:
            components.append({"type": "BUTTONS", "buttons": buttons})

    return components
