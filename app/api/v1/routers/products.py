from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies.auth import get_current_seller_id
from app.core.dependencies import get_product_service
from app.schemas.product import CharacteristicResponse, ProductCreate, ProductImageResponse, ProductResponse
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["Products"])


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать товар (без SKU → статус CREATED, на модерацию НЕ идёт)",
    operation_id="createProduct",
)
async def create_product(
    payload: ProductCreate,
    seller_id: UUID = Depends(get_current_seller_id),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    product = await service.create_product(seller_id=seller_id, payload=payload)
    return ProductResponse(
        id=product.id,
        seller_id=product.seller_id,
        category_id=product.category_id,
        title=product.title,
        slug=product.slug,
        description=product.description,
        status=product.status,
        deleted=product.deleted,
        blocked=product.blocked,
        blocking_reason_id=product.blocking_reason_id,
        moderator_comment=product.moderator_comment,
        images=[
            ProductImageResponse(id=img.id, url=img.url, ordering=img.ordering)
            for img in product.images
        ],
        characteristics=[
            CharacteristicResponse(id=c.id, name=c.name, value=c.value)
            for c in product.characteristics
        ],
        skus=[],
        created_at=product.created_at,
        updated_at=product.updated_at,
    )
