from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.middleware.error_handler import (
    domain_exception_handler,
    http_exception_handler,
)
from app.core.config import ALLOWED_ORIGINS, settings
from app.core.database import engine
from app.core.dependencies import close_moderation_client
from app.domain.exceptions import DomainException


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        yield
    finally:
        await close_moderation_client()
        await engine.dispose()


app = FastAPI(
    title="NeoMarket B2B API",
    version="1.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(DomainException, domain_exception_handler)


@app.exception_handler(HTTPException)
async def fastapi_http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = cast(list[dict[str, object]], exc.errors())
    first = errors[0] if errors else {}
    loc = first.get("loc")
    field = "unknown"
    if isinstance(loc, (list, tuple)) and loc:
        loc_parts = cast(list[object] | tuple[object, ...], loc)
        field = str(loc_parts[-1])
    message = first.get("msg", "Validation error")
    return JSONResponse(
        status_code=422,
        content={
            "code": "INVALID_REQUEST",
            "message": str(message),
            "field": field,
        },
    )


from app.api.v1.routers.inventory import router as inventory_router  # noqa: E402
from app.api.v1.routers.invoices import router as invoices_router  # noqa: E402
from app.api.v1.routers.moderation_events import (
    router as moderation_events_router,  # noqa: E402
)
from app.api.v1.routers.products import (
    public_router as public_products_router,  # noqa: E402
)
from app.api.v1.routers.products import router as products_router  # noqa: E402
from app.api.v1.routers.skus import router as skus_router  # noqa: E402

app.include_router(public_products_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(skus_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(invoices_router, prefix="/api/v1")
app.include_router(moderation_events_router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok"}
