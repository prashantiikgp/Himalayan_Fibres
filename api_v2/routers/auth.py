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
    expected = os.getenv("APP_PASSWORD", "")
    # When APP_PASSWORD is unset, accept any non-empty password — matches v1's
    # open-access behavior. Setting APP_PASSWORD enforces the gate.
    if expected and req.password != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )
    return LoginResponse(token=req.password)
