"""Smoke tests for /api/v2/email/render-preview + /test-sends (Phase 7.1)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from api_v2.main import app

    return TestClient(app)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test_secret"}


def _stamp() -> int:
    return int(time.time() * 1000)


def _seed_template(client: TestClient, headers: dict[str, str]) -> dict:
    """Create a minimal DB-only template (no .meta.yml). The variable_spec
    fallback synth path runs from `required_variables`."""
    s = _stamp()
    res = client.post(
        "/api/v2/email/templates",
        json={
            "name": f"Phase 7.1 send {s}",
            "slug": f"p71_send_{s}",
            "subject_template": "Hi {{first_name}}",
            "html_content": "<p>Hello {{first_name}} from {{contact_company}}</p>",
            "email_type": "campaign",
            "required_variables": ["first_name"],
            "category": "test",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_template_out_includes_variable_spec(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    tpl = _seed_template(client, auth_headers)
    body = client.get(
        f"/api/v2/email/templates/{tpl['id']}", headers=auth_headers
    ).json()
    assert "variable_spec" in body
    assert isinstance(body["variable_spec"], list)
    # DB-only templates synth a spec from required_variables.
    names = [v["name"] for v in body["variable_spec"]]
    assert "first_name" in names


def test_render_preview_renders_subject_and_body(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    tpl = _seed_template(client, auth_headers)
    res = client.post(
        "/api/v2/email/render-preview",
        json={
            "template_id": tpl["id"],
            "variables": {"first_name": "Prashant"},
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "Prashant" in body["subject"]
    assert "Prashant" in body["html"]


def test_render_preview_html_override_wins(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    tpl = _seed_template(client, auth_headers)
    res = client.post(
        "/api/v2/email/render-preview",
        json={
            "template_id": tpl["id"],
            "variables": {"first_name": "Studio"},
            "html_content_override": "<h1>Live edit: {{first_name}}</h1>",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "Live edit: Studio" in body["html"]


def test_render_preview_404_on_missing_template(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.post(
        "/api/v2/email/render-preview",
        json={"template_id": 9999999, "variables": {}},
        headers=auth_headers,
    )
    assert res.status_code == 404


def test_render_preview_requires_auth(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v2/email/render-preview",
            json={"template_id": 1, "variables": {}},
        ).status_code
        == 401
    )


def test_test_send_404_on_missing_contact(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    tpl = _seed_template(client, auth_headers)
    res = client.post(
        "/api/v2/email/test-sends",
        json={
            "template_id": tpl["id"],
            "contact_id": "no-such-contact",
            "variables": {},
        },
        headers=auth_headers,
    )
    assert res.status_code == 404
