from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies.auth import get_current_seller_id
from app.core.dependencies import get_sku_service
from app.domain.entities.sku import SkuEntity
from app.schemas.product import CharacteristicResponse
from app.schemas.sku import SKUCreate, SKUImageResponse, SKUResponse, SKUUpdate
from app.services.sku_service import SkuService

router = APIRouter(prefix="/skus", tags=["SKUs"])


def _sku_image_responses(sku: SkuEntity) -> list[SKUImageResponse]:
    return [
        SKUImageResponse(id=image.id, url=image.url, ordering=image.ordering)
        for image in sorted(sku.images, key=lambda image: image.ordering)
    ]


def _sku_response(sku: SkuEntity) -> SKUResponse:
    return SKUResponse(
        id=sku.id,
        product_id=sku.product_id,
        name=sku.name,
        price=sku.price,
        discount=sku.discount,
        cost_price=sku.cost_price,
        stock_quantity=sku.active_quantity + sku.reserved_quantity,
        active_quantity=sku.active_quantity,
        reserved_quantity=sku.reserved_quantity,
        article=sku.article,
        images=_sku_image_responses(sku),
        characteristics=[
            CharacteristicResponse(id=c.id, name=c.name, value=c.value)
            for c in sku.characteristics
        ],
        created_at=sku.created_at,
        updated_at=sku.updated_at,
    )


@router.post(
    "",
    response_model=SKUResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать SKU. Первый SKU товара → товар ON_MODERATION + событие CREATED",
    operation_id="createSku",
)
async def create_sku(
    payload: SKUCreate,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[SkuService, Depends(get_sku_service)],
) -> SKUResponse:
    sku = await service.create_sku(seller_id=seller_id, payload=payload)
    return _sku_response(sku)


@router.patch(
    "/{sku_id}",
    response_model=SKUResponse,
    status_code=status.HTTP_200_OK,
    summary="Обновить SKU",
    operation_id="updateSku",
)
async def update_sku(
    sku_id: UUID,
    payload: SKUUpdate,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[SkuService, Depends(get_sku_service)],
) -> SKUResponse:
    sku = await service.update_sku(seller_id=seller_id, sku_id=sku_id, payload=payload)
    return _sku_response(sku)


@router.put(
    "/{sku_id}",
    response_model=SKUResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def replace_sku(
    sku_id: UUID,
    payload: SKUUpdate,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[SkuService, Depends(get_sku_service)],
) -> SKUResponse:
    sku = await service.update_sku(
        seller_id=seller_id,
        sku_id=sku_id,
        payload=payload,
    )
    return _sku_response(sku)


@router.delete(
    "/{sku_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить SKU",
    operation_id="deleteSku",
)
async def delete_sku(
    sku_id: UUID,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[SkuService, Depends(get_sku_service)],
) -> None:
    await service.delete_sku(seller_id=seller_id, sku_id=sku_id)
