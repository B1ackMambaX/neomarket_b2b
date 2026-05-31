import secrets
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.config import settings
from app.core.security import decode_access_token

_bearer = HTTPBearer()


def _seller_id_from_token(token: str) -> UUID:
    payload = decode_access_token(token, settings.SECRET_KEY)
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing sub",
        )
    return UUID(sub)


async def get_current_seller_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> UUID:
    try:
        return _seller_id_from_token(credentials.credentials)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


async def get_seller_id_or_service_key(request: Request) -> UUID | None:
    """Returns seller_id from JWT, or None if a valid X-Service-Key is provided."""
    x_service_key = request.headers.get("X-Service-Key")
    if x_service_key is not None:
        if x_service_key == settings.B2B_TO_MOD_KEY:
            return None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service key"
        )

    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    token = authorization.removeprefix("Bearer ")
    try:
        return _seller_id_from_token(token)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


async def require_b2c_service_key(request: Request) -> None:
    x_service_key = request.headers.get("X-Service-Key") or ""
    if not secrets.compare_digest(x_service_key, settings.B2C_TO_B2B_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service key"
        )


async def require_moderation_service_key(request: Request) -> None:
    x_service_key = request.headers.get("X-Service-Key") or ""
    if not secrets.compare_digest(x_service_key, settings.B2B_TO_MOD_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service key"
        )
