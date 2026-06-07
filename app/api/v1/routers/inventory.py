from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.v1.dependencies.auth import require_b2c_service_key
from app.core.dependencies import get_inventory_service
from app.domain.exceptions import (
    IdempotencyConflictException,
    InsufficientReservedException,
    InsufficientStockException,
)
from app.schemas.inventory import (
    FailedItemDetail,
    FailedReservedItemDetail,
    FulfillRequest,
    FulfillResponse,
    ReserveItemResponse,
    ReserveRequest,
    ReserveSuccessResponse,
    UnreserveRequest,
    UnreserveResponse,
)
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.post(
    "/reserve",
    response_model=ReserveSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Зарезервировать SKU (all-or-nothing). Идемпотентно по idempotency_key.",
    operation_id="reserveInventory",
)
async def reserve_inventory(
    payload: ReserveRequest,
    _: Annotated[None, Depends(require_b2c_service_key)],
    service: Annotated[InventoryService, Depends(get_inventory_service)],
) -> ReserveSuccessResponse | JSONResponse:
    try:
        result = await service.reserve(
            idempotency_key=payload.idempotency_key,
            order_id=payload.order_id,
            items=[(item.sku_id, item.quantity) for item in payload.items],
        )
        return ReserveSuccessResponse(
            order_id=result.order_id,
            reserved_at=result.reserved_at,
            items=[
                ReserveItemResponse(
                    sku_id=item.sku_id,
                    reserved_quantity=item.quantity,
                    remaining_stock=item.remaining_stock,
                )
                for item in result.items
            ],
        )
    except InsufficientStockException as exc:
        failed = [FailedItemDetail(**fi) for fi in exc.failed_items]
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": exc.code,
                "message": str(exc),
                "details": {
                    "failed_items": [item.model_dump(mode="json") for item in failed]
                },
            },
        )


@router.post(
    "/unreserve",
    response_model=UnreserveResponse,
    status_code=status.HTTP_200_OK,
    summary="Снять резерв (при отмене заказа). Идемпотентно по order_id.",
    operation_id="unreserveInventory",
)
async def unreserve_inventory(
    payload: UnreserveRequest,
    _: Annotated[None, Depends(require_b2c_service_key)],
    service: Annotated[InventoryService, Depends(get_inventory_service)],
) -> UnreserveResponse | JSONResponse:
    try:
        result = await service.unreserve(
            order_id=payload.order_id,
            items=[(item.sku_id, item.quantity) for item in payload.items],
        )
        return UnreserveResponse(
            order_id=result.order_id,
            processed_at=result.processed_at,
        )
    except InsufficientReservedException as exc:
        failed = [FailedReservedItemDetail(**fi) for fi in exc.failed_items]
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": exc.code,
                "message": str(exc),
                "details": {
                    "failed_items": [item.model_dump(mode="json") for item in failed]
                },
            },
        )
    except IdempotencyConflictException as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"code": exc.code, "message": str(exc)},
        )


@router.post(
    "/fulfill",
    response_model=FulfillResponse,
    status_code=status.HTTP_200_OK,
    summary="Списать резерв при доставке. Идемпотентно по order_id.",
    operation_id="fulfillInventory",
)
async def fulfill_inventory(
    payload: FulfillRequest,
    _: Annotated[None, Depends(require_b2c_service_key)],
    service: Annotated[InventoryService, Depends(get_inventory_service)],
) -> FulfillResponse | JSONResponse:
    try:
        result = await service.fulfill(
            order_id=payload.order_id,
            items=[(item.sku_id, item.quantity) for item in payload.items],
        )
        return FulfillResponse(
            order_id=result.order_id,
            status="FULFILLED",
            processed_at=result.processed_at,
        )
    except InsufficientReservedException as exc:
        failed = [FailedReservedItemDetail(**fi) for fi in exc.failed_items]
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": exc.code,
                "message": str(exc),
                "details": {
                    "failed_items": [item.model_dump(mode="json") for item in failed]
                },
            },
        )
