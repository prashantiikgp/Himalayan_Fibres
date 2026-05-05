"""Unit tests for `decompose_components` (Phase 7.4).

The helper is the inverse of `build_components` and runs on every Meta
sync to populate `WATemplate` flat columns. One test per row in the
plan's mapping table, plus edge cases.
"""

from __future__ import annotations

from services.wa_template_builder import (  # type: ignore[import-not-found]
    decompose_components,
)


# ─── happy path: one test per row in the mapping table ──────────────────


def test_decompose_header_text() -> None:
    out = decompose_components(
        [{"type": "HEADER", "format": "TEXT", "text": "Hello {{1}}"}]
    )
    assert out["header_format"] == "TEXT"
    assert out["header_text"] == "Hello {{1}}"
    assert out["header_asset_url"] is None


def test_decompose_header_image() -> None:
    out = decompose_components(
        [
            {
                "type": "HEADER",
                "format": "IMAGE",
                "example": {"header_handle": ["https://cdn.meta.example/handle1"]},
            }
        ]
    )
    assert out["header_format"] == "IMAGE"
    assert out["header_text"] is None
    assert out["header_asset_url"] == "https://cdn.meta.example/handle1"


def test_decompose_header_video() -> None:
    out = decompose_components(
        [
            {
                "type": "HEADER",
                "format": "VIDEO",
                "example": {"header_handle": ["https://cdn.meta.example/v1"]},
            }
        ]
    )
    assert out["header_format"] == "VIDEO"
    assert out["header_asset_url"] == "https://cdn.meta.example/v1"


def test_decompose_header_document() -> None:
    out = decompose_components(
        [
            {
                "type": "HEADER",
                "format": "DOCUMENT",
                "example": {"header_handle": ["https://cdn.meta.example/d1"]},
            }
        ]
    )
    assert out["header_format"] == "DOCUMENT"
    assert out["header_asset_url"] == "https://cdn.meta.example/d1"


def test_decompose_body() -> None:
    out = decompose_components([{"type": "BODY", "text": "Hi {{1}}, welcome."}])
    assert out["body_text"] == "Hi {{1}}, welcome."


def test_decompose_footer() -> None:
    out = decompose_components([{"type": "FOOTER", "text": "Reply STOP to opt out"}])
    assert out["footer_text"] == "Reply STOP to opt out"


def test_decompose_buttons_quick_reply_and_url() -> None:
    btns = [
        {"type": "QUICK_REPLY", "text": "Yes please"},
        {"type": "URL", "text": "Open", "url": "https://example.com/x"},
    ]
    out = decompose_components([{"type": "BUTTONS", "buttons": btns}])
    assert out["buttons"] == btns


def test_decompose_full_template() -> None:
    """All five component types together — the realistic Meta payload."""
    out = decompose_components(
        [
            {"type": "HEADER", "format": "TEXT", "text": "Welcome {{1}}"},
            {"type": "BODY", "text": "Your sample for {{1}} is on its way."},
            {"type": "FOOTER", "text": "— Himalayan Fibres"},
            {
                "type": "BUTTONS",
                "buttons": [{"type": "QUICK_REPLY", "text": "Track order"}],
            },
        ]
    )
    assert out["header_format"] == "TEXT"
    assert out["header_text"] == "Welcome {{1}}"
    assert out["body_text"] == "Your sample for {{1}} is on its way."
    assert out["footer_text"] == "— Himalayan Fibres"
    assert out["buttons"] == [{"type": "QUICK_REPLY", "text": "Track order"}]


# ─── edge cases ─────────────────────────────────────────────────────────


def test_decompose_empty_or_none() -> None:
    """No components → all flat columns at safe defaults."""
    for arg in (None, []):
        out = decompose_components(arg)
        assert out == {
            "body_text": "",
            "header_format": None,
            "header_text": None,
            "header_asset_url": None,
            "footer_text": None,
            "buttons": [],
        }


def test_decompose_skips_component_missing_type() -> None:
    out = decompose_components(
        [
            {"text": "no type field"},
            {"type": "BODY", "text": "ok"},
        ]
    )
    assert out["body_text"] == "ok"


def test_decompose_skips_non_dict_entries() -> None:
    out = decompose_components(["not a dict", None, {"type": "BODY", "text": "ok"}])
    assert out["body_text"] == "ok"


def test_decompose_duplicate_header_first_wins() -> None:
    out = decompose_components(
        [
            {"type": "HEADER", "format": "TEXT", "text": "first"},
            {"type": "HEADER", "format": "TEXT", "text": "second"},
        ]
    )
    assert out["header_text"] == "first"


def test_decompose_duplicate_body_first_wins() -> None:
    out = decompose_components(
        [
            {"type": "BODY", "text": "first body"},
            {"type": "BODY", "text": "second body"},
        ]
    )
    assert out["body_text"] == "first body"


def test_decompose_unknown_button_type_preserved() -> None:
    """Future Meta button types (e.g. CATALOG, FLOW) shouldn't be dropped."""
    btns = [
        {"type": "FLOW", "text": "Open form", "flow_id": "abc"},
        {"type": "QUICK_REPLY", "text": "No thanks"},
    ]
    out = decompose_components([{"type": "BUTTONS", "buttons": btns}])
    assert out["buttons"] == btns


def test_decompose_unknown_top_level_component_skipped() -> None:
    """Carousel / limited-time-offer components today aren't supported —
    they should be ignored, not crash."""
    out = decompose_components(
        [
            {"type": "CAROUSEL", "cards": []},
            {"type": "BODY", "text": "still works"},
        ]
    )
    assert out["body_text"] == "still works"


def test_decompose_header_image_missing_handle() -> None:
    """Media header with no example.header_handle → URL stays empty."""
    out = decompose_components([{"type": "HEADER", "format": "IMAGE"}])
    assert out["header_format"] == "IMAGE"
    assert out["header_asset_url"] == ""


def test_decompose_header_format_case_insensitive() -> None:
    """Meta returns formats uppercase, but be defensive."""
    out = decompose_components(
        [{"type": "header", "format": "text", "text": "hi"}]
    )
    assert out["header_format"] == "TEXT"
    assert out["header_text"] == "hi"


def test_decompose_buttons_drops_non_dict_entries() -> None:
    out = decompose_components(
        [
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Yes"},
                    "not a dict",
                    None,
                ],
            }
        ]
    )
    assert out["buttons"] == [{"type": "QUICK_REPLY", "text": "Yes"}]
