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

    Fail-closed by default (review fix M1). The startup gate in api_v2/main.py
    refuses to boot if APP_PASSWORD is unset AND APP_OPEN_ACCESS is not
    explicitly true — so by the time this dependency runs, either:
      (a) APP_PASSWORD is set → token must match, or
      (b) APP_OPEN_ACCESS=true and APP_PASSWORD is unset → open access.
    """
    expected = os.getenv("APP_PASSWORD", "").strip()
    open_access = os.getenv("APP_OPEN_ACCESS", "").strip().lower() in {"1", "true", "yes"}
    if not expected and open_access:
        # Explicitly opted into open access. Startup logged a warning.
        return
    if not expected:
        # Should be unreachable — main.py refuses to start in this state —
        # but defense in depth.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth misconfigured (APP_PASSWORD unset, APP_OPEN_ACCESS not enabled)",
        )
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
