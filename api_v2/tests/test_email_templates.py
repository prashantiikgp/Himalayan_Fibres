"""Smoke tests for /api/v2/email/templates (Phase 6.4)."""

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


def test_create_email_template(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    s = _stamp()
    res = client.post(
        "/api/v2/email/templates",
        json={
            "name": f"Phase 6.4 test {s}",
            "slug": f"phase64_{s}",
            "subject_template": "Hello {{first_name}}",
            "html_content": "<p>Body for {{first_name}}</p>",
            "email_type": "campaign",
            "required_variables": ["first_name"],
            "category": "test",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["slug"] == f"phase64_{s}"
    assert body["is_active"] is True
    assert body["required_variables"] == ["first_name"]


def test_create_duplicate_slug_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    s = _stamp()
    body = {"name": f"dup {s}", "slug": f"phase64_dup_{s}"}
    first = client.post("/api/v2/email/templates", json=body, headers=auth_headers)
    assert first.status_code == 201
    second = client.post("/api/v2/email/templates", json=body, headers=auth_headers)
    assert second.status_code == 409


def test_create_missing_required_400(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    res = client.post(
        "/api/v2/email/templates",
        json={"name": "no slug"},
        headers=auth_headers,
    )
    assert res.status_code == 400
    res = client.post(
        "/api/v2/email/templates",
        json={"slug": "no_name"},
        headers=auth_headers,
    )
    assert res.status_code == 400


def test_save_in_place(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    s = _stamp()
    create = client.post(
        "/api/v2/email/templates",
        json={"name": f"to-edit {s}", "slug": f"phase64_edit_{s}", "html_content": "v1"},
        headers=auth_headers,
    )
    tid = create.json()["id"]

    save = client.post(
        f"/api/v2/email/templates/{tid}/save",
        json={"html_content": "v2", "subject_template": "edited"},
        headers=auth_headers,
    )
    assert save.status_code == 200
    body = save.json()
    assert body["id"] == tid
    assert body["html_content"] == "v2"
    assert body["subject_template"] == "edited"


def test_get_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    res = client.get("/api/v2/email/templates/9999999", headers=auth_headers)
    assert res.status_code == 404


def test_delete_round_trip(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    s = _stamp()
    create = client.post(
        "/api/v2/email/templates",
        json={"name": f"to-delete {s}", "slug": f"phase64_del_{s}"},
        headers=auth_headers,
    )
    tid = create.json()["id"]

    res = client.delete(
        f"/api/v2/email/templates/{tid}", headers=auth_headers
    )
    assert res.status_code == 204
    assert (
        client.get(
            f"/api/v2/email/templates/{tid}", headers=auth_headers
        ).status_code
        == 404
    )


def test_list_active_only(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    s = _stamp()
    client.post(
        "/api/v2/email/templates",
        json={"name": f"active {s}", "slug": f"act_{s}", "is_active": True},
        headers=auth_headers,
    )
    client.post(
        "/api/v2/email/templates",
        json={"name": f"inactive {s}", "slug": f"inact_{s}", "is_active": False},
        headers=auth_headers,
    )
    body = client.get(
        "/api/v2/email/templates?active_only=true", headers=auth_headers
    ).json()
    for t in body["templates"]:
        assert t["is_active"] is True


def test_email_templates_require_auth(client: TestClient) -> None:
    assert client.get("/api/v2/email/templates").status_code == 401
    assert (
        client.post("/api/v2/email/templates", json={"name": "x", "slug": "y"}).status_code
        == 401
    )
