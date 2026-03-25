import secrets
from typing import Optional
from fastapi import HTTPException, Header
from app.config import settings


def require_admin(x_admin_key: Optional[str] = Header(None)) -> str:
    """Dependency to require admin authentication via X-Admin-Key header."""
    if x_admin_key is None:
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")
    if not secrets.compare_digest(x_admin_key, settings.REGISTRY_ADMIN_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing admin key")
    return x_admin_key
