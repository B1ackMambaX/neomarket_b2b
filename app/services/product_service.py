import re
from typing import cast
from uuid import UUID

from app.domain.entities.category import CategoryEntity
from app.domain.entities.product import (
    CharacteristicEntity,
    FieldReportEntity,
    ProductEntity,
    ProductImageEntity,
)
from app.domain.entities.sku import SkuEntity
from app.domain.events import AbstractEventPublisher
from app.domain.exceptions import (
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.domain.repositories.category_repo import AbstractCategoryRepository
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.seller_repo import AbstractSellerRepository
from app.domain.utils.datetime import utc_now
from app.domain.value_objects.product_status import ProductStatus
from app.schemas.product import ModerationEventRequest, ProductCreate, ProductUpdate


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


class ProductService:
    def __init__(
        self,
        product_repo: AbstractProductRepository,
        seller_repo: AbstractSellerRepository,
        category_repo: AbstractCategoryRepository,
        event_publisher: AbstractEventPublisher | None = None,
    ) -> None:
        self._product_repo: AbstractProductRepository = product_repo
        self._seller_repo: AbstractSellerRepository = seller_repo
        self._category_repo: AbstractCategoryRepository = category_repo
        self._event_publisher: AbstractEventPublisher | None = event_publisher

    async def create_product(
        self, seller_id: UUID, payload: ProductCreate
    ) -> ProductEntity:
        _ = await self._seller_repo.get_or_raise(seller_id)

        if not payload.images:
            raise ValidationException("At least one image is required")

        _ = await self._category_repo.get_or_raise(payload.category_id)

        product = ProductEntity.create(
            seller_id=seller_id,
            category_id=payload.category_id,
            title=payload.title,
            description=payload.description,
            slug=payload.slug or _slugify(payload.title),
            characteristics=[
                CharacteristicEntity(name=c.name, value=c.value)
                for c in payload.characteristics
            ],
        )
        for img in payload.images:
            product.images.append(
                ProductImageEntity(
                    product_id=product.id, url=img.url, ordering=img.ordering
                )
            )

        return await self._product_repo.save(product)

    async def update_product(
        self,
        seller_id: UUID,
        product_id: UUID,
        payload: ProductUpdate,
    ) -> ProductEntity:
        product = await self._product_repo.get_or_raise(product_id)
        if product.seller_id != seller_id:
            raise NotFoundException("Product not found")
        if product.status == ProductStatus.HARD_BLOCKED:
            raise ForbiddenException("Cannot edit hard-blocked product")
        if payload.title is not None:
            product.title = payload.title
            product.slug = _slugify(payload.title)
        if payload.description is not None:
            product.description = payload.description
        if payload.category_id is not None:
            _ = await self._category_repo.get_or_raise(payload.category_id)
            product.category_id = payload.category_id
        if payload.characteristics is not None:
            product.characteristics = [
                CharacteristicEntity(name=c.name, value=c.value)
                for c in payload.characteristics
            ]
        product.updated_at = utc_now()
        return await self._product_repo.save(product)

    async def delete_product(self, seller_id: UUID, product_id: UUID) -> None:
        product = await self._product_repo.get_or_raise(product_id)
        if product.seller_id != seller_id:
            raise NotFoundException("Product not found")
        if product.status == ProductStatus.HARD_BLOCKED:
            raise ForbiddenException("Cannot delete hard-blocked product")
        product.deleted = True
        product.updated_at = utc_now()
        _ = await self._product_repo.save(product)

    async def get_product(
        self, seller_id: UUID | None, product_id: UUID
    ) -> tuple[ProductEntity, CategoryEntity]:
        product = await self._product_repo.get_with_skus_and_reports(product_id)
        if product is None:
            raise NotFoundException("Product not found")
        if seller_id is not None and product.seller_id != seller_id:
            raise NotFoundException("Product not found")
        category = await self._category_repo.get_by_id(product.category_id)
        if category is None:
            category = CategoryEntity(id=product.category_id, name="")
        return product, category

    async def list_catalog_products(
        self,
        ids: list[UUID] | None = None,
        category_id: UUID | None = None,
        seller_id: UUID | None = None,
        search: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        characteristic_filters: dict[str, list[str]] | None = None,
        sort: str = "created_desc",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[ProductEntity, CategoryEntity]], int]:
        products, total_count = await self._product_repo.list_catalog_visible(
            ids=ids,
            category_id=category_id,
            seller_id=seller_id,
            search=search,
            min_price=min_price,
            max_price=max_price,
            characteristic_filters=characteristic_filters,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        return [
            (product, CategoryEntity(id=product.category_id, name=""))
            for product in products
        ], total_count

    async def apply_moderation_event(self, payload: ModerationEventRequest) -> bool:
        product = await self._product_repo.get_with_skus_and_reports(payload.product_id)
        if product is None:
            raise NotFoundException("Product not found")
        if (
            payload.event_type == ProductStatus.BLOCKED.value
            and payload.blocking_reason_id is None
        ):
            raise ValidationException(
                "blocking_reason_id is required for BLOCKED event"
            )

        is_new_event = await self._product_repo.mark_moderation_event_processed(
            payload.idempotency_key
        )
        if not is_new_event:
            return False

        if payload.event_type == ProductStatus.MODERATED.value:
            product.status = ProductStatus.MODERATED
            product.blocked = False
            product.blocking_reason_id = None
            product.blocking_reason_title = None
            product.moderator_comment = None
            product.field_reports = []
            product.moderated_at = payload.occurred_at
        else:
            product.status = (
                ProductStatus.HARD_BLOCKED
                if payload.hard_block
                else ProductStatus.BLOCKED
            )
            product.blocked = True
            product.blocking_reason_id = payload.blocking_reason_id
            product.moderator_comment = payload.moderator_comment
            product.field_reports = [
                FieldReportEntity(
                    product_id=product.id,
                    field_name=report.field_name,
                    sku_id=report.sku_id,
                    comment=report.comment,
                )
                for report in (payload.field_reports or [])
            ]

        product.updated_at = utc_now()
        _ = await self._product_repo.save(product)

        if (
            payload.event_type == ProductStatus.BLOCKED.value
            and self._event_publisher is not None
        ):
            await self._event_publisher.publish_product_blocked(
                product_id=product.id,
                sku_ids=[sku.id for sku in cast(list[SkuEntity], product.skus)],
                hard_block=payload.hard_block,
            )
        return True
