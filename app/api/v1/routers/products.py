from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies.auth import get_current_seller_id
from app.core.dependencies import get_product_service
from app.schemas.product import ProductCreate, ProductImageResponse, ProductResponse, SkuResponse
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["Products"])


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать товар",
    description="Создаёт новый товар со статусом DRAFT. Товар принадлежит продавцу из заголовка X-Seller-ID.",
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
        description=product.description,
        status=product.status,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get(
    "/{id}",
    response_model=ProductResponse,
    summary="Получить товар",
)
async def get_product(
    id: UUID,
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    product = await service.get_product_by_id(id)

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductResponse(
        id=product.id,
        seller_id=product.seller_id,
        category_id=product.category_id,
        title=product.title,
        description=product.description,
        status=product.status,
        created_at=product.created_at,
        updated_at=product.updated_at,
        images=[
            ProductImageResponse(
                id=image.id,
                url=image.url,
                ordering=image.ordering,
            )
            for image in product.images
        ],
        skus=[
            SkuResponse(
                id=sku.id,
                name=sku.name,
                price=sku.price,
                active_quantity=sku.active_quantity,
                is_active=sku.is_active,
            )
            for sku in product.skus
        ],
    )
