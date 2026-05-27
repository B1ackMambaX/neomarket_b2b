from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import cast

from jose import jwt

_ALGORITHM = "HS256"


def create_access_token(
    data: Mapping[str, object], secret_key: str, expires_minutes: int = 30
) -> str:
    payload: dict[str, object] = dict(data)
    payload["exp"] = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    return jwt.encode(payload, secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> dict[str, object]:
    return cast(
        dict[str, object], jwt.decode(token, secret_key, algorithms=[_ALGORITHM])
    )
