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
# Tests boot api_v2 once; main.py's fail-closed gate (review fix M1) needs
# one of these set BEFORE main.py is imported.
os.environ.setdefault("APP_PASSWORD", "test_secret")


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


def test_login_with_password_set(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_PASSWORD set: only the matching password gets a token."""
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    monkeypatch.delenv("APP_OPEN_ACCESS", raising=False)
    bad = client.post("/api/v2/auth/login", json={"password": "wrong"})
    assert bad.status_code == 401
    good = client.post("/api/v2/auth/login", json={"password": "secret123"})
    assert good.status_code == 200
    assert good.json() == {"token": "secret123"}


def test_login_open_access_explicit_optin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """APP_OPEN_ACCESS=true + APP_PASSWORD unset = any password accepted."""
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("APP_OPEN_ACCESS", "true")
    res = client.post("/api/v2/auth/login", json={"password": "anything"})
    assert res.status_code == 200
    assert res.json() == {"token": "anything"}


def test_login_fails_closed_when_misconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both APP_PASSWORD unset AND APP_OPEN_ACCESS not true = 503 (M1)."""
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("APP_OPEN_ACCESS", raising=False)
    res = client.post("/api/v2/auth/login", json={"password": "anything"})
    assert res.status_code == 503
