from typing import Final

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    ConflictException,
    DomainException,
    ForbiddenException,
    IdempotencyConflictException,
    InvalidProductStateException,
    InsufficientReservedException,
    NotFoundException,
    NotOwnerException,
    PermissionDeniedException,
)

_DOMAIN_STATUS_MAP: Final[dict[type[DomainException], int]] = {
    NotFoundException: 404,
    PermissionDeniedException: 403,
    NotOwnerException: 403,
    ForbiddenException: 403,
    ConflictException: 409,
    InvalidProductStateException: 409,
    InsufficientReservedException: 409,
    IdempotencyConflictException: 409,
}

_HTTP_CODE_MAP: Final[dict[int, str]] = {
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
}


async def domain_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainException)
    status_code = _DOMAIN_STATUS_MAP.get(type(exc), 400)
    return JSONResponse(
        status_code=status_code,
        content={"code": exc.code, "message": str(exc)},
    )


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": code, "message": exc.detail},
    )
