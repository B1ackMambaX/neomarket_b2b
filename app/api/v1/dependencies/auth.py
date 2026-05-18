from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.config import settings
from app.core.security import decode_access_token

_bearer = HTTPBearer()


async def get_current_seller_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UUID:
    try:
        payload = decode_access_token(credentials.credentials, settings.SECRET_KEY)
        sub: str | None = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing sub")
        return UUID(sub)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_seller_id_or_service_key(request: Request) -> UUID | None:
    """Returns seller_id from JWT, or None if a valid X-Service-Key is provided."""
    x_service_key = request.headers.get("X-Service-Key")
    if x_service_key is not None:
        if x_service_key == settings.B2B_TO_MOD_KEY:
            return None
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service key")

    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token, settings.SECRET_KEY)
        sub: str | None = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing sub")
        return UUID(sub)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
