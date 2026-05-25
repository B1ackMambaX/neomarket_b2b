from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies.auth import get_current_seller_id
from app.core.dependencies import get_sku_service
from app.schemas.product import CharacteristicResponse
from app.schemas.sku import SKUCreate, SKUImageResponse, SKUResponse
from app.services.sku_service import SkuService

router = APIRouter(prefix="/skus", tags=["SKUs"])


@router.post(
    "",
    response_model=SKUResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать SKU. Первый SKU товара → товар ON_MODERATION + событие CREATED",
    operation_id="createSku",
)
async def create_sku(
    payload: SKUCreate,
    seller_id: UUID = Depends(get_current_seller_id),
    service: SkuService = Depends(get_sku_service),
) -> SKUResponse:
    sku = await service.create_sku(seller_id=seller_id, payload=payload)
    images = (
        [SKUImageResponse(id=uuid4(), url=sku.image, ordering=0)]
        if sku.image
        else []
    )
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
        images=images,
        characteristics=[
            CharacteristicResponse(id=c.id, name=c.name, value=c.value)
            for c in sku.characteristics
        ],
        created_at=sku.created_at,
        updated_at=sku.updated_at,
    )
