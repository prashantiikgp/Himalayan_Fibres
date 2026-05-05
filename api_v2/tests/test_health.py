"""Endpoint smoke tests for /api/v2/health and /api/v2/auth/login."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure the test environment matches main.py's sys.path setup.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HF_DASHBOARD = _REPO_ROOT / "hf_dashboard"
if _HF_DASHBOARD.exists() and str(_HF_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_HF_DASHBOARD))

# Use SQLite for tests so we don't hit prod Postgres.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_HF_DASHBOARD / 'data' / 'test.db'}")


@pytest.fixture()
def client() -> TestClient:
    from api_v2.main import app

    return TestClient(app)


def test_health_returns_200(client: TestClient) -> None:
    res = client.get("/api/v2/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_login_open_access(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """When APP_PASSWORD is unset, any non-empty password is accepted."""
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    res = client.post("/api/v2/auth/login", json={"password": "anything"})
    assert res.status_code == 200
    assert res.json() == {"token": "anything"}


def test_login_with_password_set(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    bad = client.post("/api/v2/auth/login", json={"password": "wrong"})
    assert bad.status_code == 401
    good = client.post("/api/v2/auth/login", json={"password": "secret123"})
    assert good.status_code == 200
    assert good.json() == {"token": "secret123"}
