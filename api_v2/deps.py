"""FastAPI dependencies — auth, DB session.

Auth lifecycle per STANDARDS §1: Bearer token in `Authorization` header
checked against APP_PASSWORD env var. 401 with WWW-Authenticate header
on missing/wrong token.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.database import get_db  # type: ignore[import-not-found]

_bearer = HTTPBearer(auto_error=False)


def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    """Validate the Bearer token equals APP_PASSWORD.

    APP_PASSWORD unset = open access (matches v1 behavior). Set it via
    HF Space Secrets to gate the API.
    """
    expected = os.getenv("APP_PASSWORD", "")
    if not expected:
        # Open access — v1 also runs this way until APP_PASSWORD is set.
        return
    if credentials is None or credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_db_session():
    """Yield a DB session that closes after the request. SQLAlchemy session."""
    db = get_db()
    try:
        yield db
    finally:
        db.close()


AuthDep = Annotated[None, Depends(require_auth)]
DbDep = Annotated[object, Depends(get_db_session)]
