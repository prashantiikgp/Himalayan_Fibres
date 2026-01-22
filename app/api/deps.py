"""API dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

# Database session dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]
