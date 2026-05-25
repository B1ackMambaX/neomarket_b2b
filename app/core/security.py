from datetime import datetime, timedelta

from jose import jwt

_ALGORITHM = "HS256"


def create_access_token(data: dict, secret_key: str, expires_minutes: int = 30) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=expires_minutes)
    return jwt.encode(payload, secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str, secret_key: str) -> dict:
    return jwt.decode(token, secret_key, algorithms=[_ALGORITHM])
