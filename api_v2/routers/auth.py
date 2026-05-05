"""POST /api/v2/auth/login — Bearer token issuance.

Per STANDARDS §1: token = APP_PASSWORD. The "issuance" is just a check —
on success we echo the password back as the token, which the frontend
stores in localStorage.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    token: str


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    """Issue a Bearer token = APP_PASSWORD on a successful password check.

    Fail-closed by default (review fix M1). When APP_OPEN_ACCESS=true and
    APP_PASSWORD is unset, any non-empty password is accepted and echoed back
    as the token. Otherwise the password must match APP_PASSWORD exactly.
    """
    expected = os.getenv("APP_PASSWORD", "").strip()
    open_access = os.getenv("APP_OPEN_ACCESS", "").strip().lower() in {"1", "true", "yes"}
    if not expected and not open_access:
        # Should be unreachable — main.py refuses to start in this state.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth misconfigured",
        )
    if expected and req.password != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )
    return LoginResponse(token=req.password)
