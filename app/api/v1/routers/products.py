from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies.auth import get_current_seller_id, get_seller_id_or_service_key
from app.core.dependencies import get_product_service
from app.schemas.product import (
    BlockingReasonInProductResponse,
    CategoryInProductResponse,
    CharacteristicResponse,
    FieldReportResponse,
    ProductCreate,
    ProductDetailResponse,
    ProductImageResponse,
    ProductResponse,
)
from app.schemas.sku import SKUImageResponse, SKUResponse
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


@router.get(
    "/{product_id}",
    response_model=ProductDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Карточка товара (seller — полная, X-Service-Key — без IDOR-проверки)",
    operation_id="getProduct",
)
async def get_product(
    product_id: UUID,
    seller_id: UUID | None = Depends(get_seller_id_or_service_key),
    service: ProductService = Depends(get_product_service),
) -> ProductDetailResponse:
    product, category = await service.get_product(seller_id=seller_id, product_id=product_id)

    blocking_reason = None
    if product.blocking_reason_id is not None:
        blocking_reason = BlockingReasonInProductResponse(
            id=product.blocking_reason_id,
            title=product.blocking_reason_title or "",
            comment=product.moderator_comment,
        )

    skus = [
        SKUResponse(
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
            images=(
                [SKUImageResponse(id=uuid4(), url=sku.image, ordering=0)]
                if sku.image
                else []
            ),
            characteristics=[
                CharacteristicResponse(id=c.id, name=c.name, value=c.value)
                for c in sku.characteristics
            ],
            created_at=sku.created_at,
            updated_at=sku.updated_at,
        )
        for sku in product.skus
    ]

    return ProductDetailResponse(
        id=product.id,
        seller_id=product.seller_id,
        category_id=product.category_id,
        title=product.title,
        slug=product.slug,
        description=product.description,
        status=product.status,
        deleted=product.deleted,
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
        skus=skus,
        created_at=product.created_at,
        updated_at=product.updated_at,
        blocked=product.blocked,
        category=CategoryInProductResponse(id=category.id, name=category.name),
        blocking_reason=blocking_reason,
        field_reports=[
            FieldReportResponse(
                field_name=r.field_name,
                sku_id=r.sku_id,
                comment=r.comment,
            )
            for r in product.field_reports
        ],
    )
