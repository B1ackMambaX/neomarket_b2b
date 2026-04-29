from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies.auth import get_current_seller_id
from app.core.dependencies import get_product_service
from app.schemas.product import SkuCreate, SkuResponse, SkuUpdate
from app.services.product_service import ProductService

router = APIRouter(prefix="/skus", tags=["SKUs"])


@router.post(
    "/",
    response_model=SkuResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать SKU",
)
async def create_sku(
    payload: SkuCreate,
    seller_id: UUID = Depends(get_current_seller_id),
    service: ProductService = Depends(get_product_service),
) -> SkuResponse:
    sku = await service.create_sku(product_id=payload.product_id, payload=payload)
    return SkuResponse(
        id=sku.id,
        name=sku.name,
        price=sku.price,
        active_quantity=sku.active_quantity,
        is_active=sku.is_active,
    )


@router.put(
    "/{sku_id}",
    response_model=SkuResponse,
    summary="Обновить SKU",
)
async def update_sku(
    sku_id: UUID,
    payload: SkuUpdate,
    seller_id: UUID = Depends(get_current_seller_id),
    service: ProductService = Depends(get_product_service),
) -> SkuResponse:
    sku = await service.update_sku(sku_id=sku_id, payload=payload)
    return SkuResponse(
        id=sku.id,
        name=sku.name,
        price=sku.price,
        active_quantity=sku.active_quantity,
        is_active=sku.is_active,
    )