from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.v1.dependencies.auth import (
    get_current_seller_id,
    get_seller_id_or_service_key,
    require_b2c_service_key,
)
from app.core.dependencies import get_product_service
from app.domain.entities.product import ProductEntity
from app.domain.entities.sku import SkuEntity
from app.domain.value_objects.product_status import ProductStatus
from app.schemas.product import (
    BlockingReasonInProductResponse,
    CategoryInProductResponse,
    CharacteristicResponse,
    FieldReportResponse,
    ProductCreate,
    ProductDetailResponse,
    ProductImageResponse,
    ProductPaginatedResponse,
    ProductPublicBatchRequest,
    ProductPublicPaginatedResponse,
    ProductPublicResponse,
    ProductPublicShortResponse,
    ProductResponse,
    ProductShortResponse,
    ProductUpdate,
)
from app.schemas.sku import SKUImageResponse, SKUPublicResponse, SKUResponse
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["Products"])
public_router = APIRouter(prefix="/public/products", tags=["Public Catalog"])


async def _parse_characteristic_filters(request: Request) -> dict[str, list[str]]:
    """Parse deepObject query params: ?filters[brand]=apple&filters[brand]=samsung."""
    filters: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        if key.startswith("filters[") and key.endswith("]"):
            char_name = key[8:-1]
            if char_name:
                filters.setdefault(char_name, []).append(value)
    return filters


def _sku_image_responses(sku: SkuEntity) -> list[SKUImageResponse]:
    return [
        SKUImageResponse(id=image.id, url=image.url, ordering=image.ordering)
        for image in sorted(sku.images, key=lambda image: image.ordering)
    ]


def _product_skus(product: ProductEntity) -> list[SkuEntity]:
    return cast(list[SkuEntity], product.skus)


def _public_product_response(product: ProductEntity) -> ProductPublicResponse:
    skus = _product_skus(product)
    return ProductPublicResponse(
        id=product.id,
        seller_id=product.seller_id,
        category_id=product.category_id,
        title=product.title,
        slug=product.slug,
        description=product.description,
        status=product.status,
        images=[
            ProductImageResponse(id=img.id, url=img.url, ordering=img.ordering)
            for img in product.images
        ],
        characteristics=[
            CharacteristicResponse(id=c.id, name=c.name, value=c.value)
            for c in product.characteristics
        ],
        skus=[
            SKUPublicResponse(
                id=sku.id,
                product_id=sku.product_id,
                name=sku.name,
                price=sku.price,
                discount=sku.discount,
                stock_quantity=sku.active_quantity + sku.reserved_quantity,
                active_quantity=sku.active_quantity,
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
            )
            for sku in skus
            if sku.active_quantity > 0
        ],
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _public_product_short_response(
    product: ProductEntity,
) -> ProductPublicShortResponse:
    active_skus = [sku for sku in _product_skus(product) if sku.active_quantity > 0]
    min_price = min((sku.price for sku in active_skus), default=None)
    cover_image = None
    if product.images:
        cover_image = min(product.images, key=lambda image: image.ordering).url
    return ProductPublicShortResponse(
        id=product.id,
        title=product.title,
        slug=product.slug,
        status=product.status,
        category_id=product.category_id,
        min_price=min_price,
        cover_image=cover_image,
        created_at=product.created_at,
    )


def _seller_product_short_response(product: ProductEntity) -> ProductShortResponse:
    skus = _product_skus(product)
    return ProductShortResponse(
        id=product.id,
        title=product.title,
        slug=product.slug,
        status=product.status,
        category_id=product.category_id,
        deleted=product.deleted,
        created_at=product.created_at,
        min_price=min((sku.price for sku in skus), default=None),
        cover_image=(
            min(product.images, key=lambda image: image.ordering).url
            if product.images
            else None
        ),
    )


def _product_response(product: ProductEntity) -> ProductResponse:
    return ProductResponse(
        id=product.id,
        seller_id=product.seller_id,
        category_id=product.category_id,
        title=product.title,
        slug=product.slug or "",
        description=product.description or "",
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


@public_router.get(
    "",
    response_model=ProductPublicPaginatedResponse,
    status_code=status.HTTP_200_OK,
    summary="Витрина — только MODERATED, не deleted, active_quantity > 0",
    operation_id="listPublicProducts",
)
async def list_catalog_products(
    _: Annotated[None, Depends(require_b2c_service_key)],
    characteristic_filters: Annotated[
        dict[str, list[str]], Depends(_parse_characteristic_filters)
    ],
    service: Annotated[ProductService, Depends(get_product_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    category_id: UUID | None = None,
    search: Annotated[str | None, Query(min_length=3)] = None,
    min_price: Annotated[int | None, Query(ge=0)] = None,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    seller_id: UUID | None = None,
    sort: Annotated[
        str, Query(pattern="^(price_asc|price_desc|created_desc|popular)$")
    ] = "created_desc",
) -> ProductPublicPaginatedResponse:
    items, total_count = await service.list_catalog_products(
        category_id=category_id,
        seller_id=seller_id,
        search=search,
        min_price=min_price,
        max_price=max_price,
        characteristic_filters=characteristic_filters or None,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return ProductPublicPaginatedResponse(
        items=[_public_product_short_response(product) for product, _ in items],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


@public_router.post(
    "/batch",
    response_model=list[ProductPublicResponse],
    status_code=status.HTTP_200_OK,
    summary="Batch-получение карточек по списку product_id для B2C",
    operation_id="batchPublicProducts",
)
async def batch_catalog_products(
    payload: ProductPublicBatchRequest,
    _: Annotated[None, Depends(require_b2c_service_key)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> list[ProductPublicResponse]:
    items, _total_count = await service.list_catalog_products(
        ids=payload.product_ids,
        limit=len(payload.product_ids) or 1,
        offset=0,
    )
    return [_public_product_response(product) for product, _ in items]


@router.get(
    "",
    response_model=ProductPaginatedResponse,
    status_code=status.HTTP_200_OK,
    summary="Список своих товаров",
    operation_id="listMyProducts",
)
async def list_seller_products(
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[ProductService, Depends(get_product_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    product_status: Annotated[
        ProductStatus | None, Query(alias="status")
    ] = None,
    include_deleted: bool = False,
) -> ProductPaginatedResponse:
    products, total_count = await service.list_seller_products(
        seller_id=seller_id,
        status=product_status,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )
    return ProductPaginatedResponse(
        items=[_seller_product_short_response(product) for product in products],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать товар (без SKU → статус CREATED, на модерацию НЕ идёт)",
    operation_id="createProduct",
)
async def create_product(
    payload: ProductCreate,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductResponse:
    product = await service.create_product(seller_id=seller_id, payload=payload)
    return _product_response(product)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Редактирование товара",
    operation_id="updateProduct",
)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductResponse:
    product = await service.update_product(
        seller_id=seller_id, product_id=product_id, payload=payload
    )
    return _product_response(product)


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def replace_product(
    product_id: UUID,
    payload: ProductUpdate,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductResponse:
    product = await service.update_product(
        seller_id=seller_id, product_id=product_id, payload=payload
    )
    return _product_response(product)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Мягкое удаление товара",
    operation_id="deleteProduct",
)
async def delete_product(
    product_id: UUID,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> None:
    await service.delete_product(seller_id=seller_id, product_id=product_id)


@router.get(
    "/{product_id}",
    response_model=ProductDetailResponse | ProductPublicResponse,
    status_code=status.HTTP_200_OK,
    summary="Карточка товара (seller — полная, X-Service-Key — без cеллерских полей)",
    operation_id="getProduct",
)
async def get_product(
    product_id: UUID,
    seller_id: Annotated[UUID | None, Depends(get_seller_id_or_service_key)],
    service: Annotated[ProductService, Depends(get_product_service)],
) -> ProductDetailResponse | ProductPublicResponse:
    product, category = await service.get_product(
        seller_id=seller_id, product_id=product_id
    )

    if seller_id is None:
        public_skus = [
            SKUPublicResponse(
                id=sku.id,
                product_id=sku.product_id,
                name=sku.name,
                price=sku.price,
                discount=sku.discount,
                stock_quantity=sku.active_quantity + sku.reserved_quantity,
                active_quantity=sku.active_quantity,
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
            )
            for sku in _product_skus(product)
        ]
        return ProductPublicResponse(
            id=product.id,
            seller_id=product.seller_id,
            category_id=product.category_id,
            title=product.title,
            slug=product.slug,
            description=product.description,
            status=product.status,
            images=[
                ProductImageResponse(id=img.id, url=img.url, ordering=img.ordering)
                for img in product.images
            ],
            characteristics=[
                CharacteristicResponse(id=c.id, name=c.name, value=c.value)
                for c in product.characteristics
            ],
            skus=public_skus,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )

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
            images=_sku_image_responses(sku),
            characteristics=[
                CharacteristicResponse(id=c.id, name=c.name, value=c.value)
                for c in sku.characteristics
            ],
            created_at=sku.created_at,
            updated_at=sku.updated_at,
        )
        for sku in _product_skus(product)
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
