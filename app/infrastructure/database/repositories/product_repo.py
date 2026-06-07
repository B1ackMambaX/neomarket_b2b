from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.product import (
    CharacteristicEntity,
    FieldReportEntity,
    ProductEntity,
    ProductImageEntity,
)
from app.domain.entities.sku import SkuImageEntity
from app.domain.exceptions import NotFoundException
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.value_objects.product_status import ProductStatus
from app.infrastructure.database.models.product import ProductModel
from app.infrastructure.database.models.product_characteristic import (
    ProductCharacteristicModel,
)
from app.infrastructure.database.models.moderation_event import ModerationEventModel
from app.infrastructure.database.models.product_image import ProductImageModel
from app.infrastructure.database.models.product_field_report import ProductFieldReportModel
from app.infrastructure.database.models.sku import SkuModel


class SQLAlchemyProductRepository(AbstractProductRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, product_id: UUID) -> ProductEntity | None:
        result = await self._session.execute(
            select(ProductModel)
            .options(
                selectinload(ProductModel.images),
                selectinload(ProductModel.characteristics),
            )
            .where(ProductModel.id == product_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_id_for_update(self, product_id: UUID) -> ProductEntity | None:
        result = await self._session.execute(
            select(ProductModel)
            .options(
                selectinload(ProductModel.images),
                selectinload(ProductModel.characteristics),
            )
            .where(ProductModel.id == product_id)
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_or_raise(self, product_id: UUID) -> ProductEntity:
        entity = await self.get_by_id(product_id)
        if entity is None:
            raise NotFoundException(f"Product {product_id} not found")
        return entity

    async def list_by_seller(
        self,
        seller_id: UUID,
        status: ProductStatus | None = None,
        include_deleted: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ProductEntity], int]:
        query = (
            select(ProductModel)
            .options(
                selectinload(ProductModel.images),
                selectinload(ProductModel.characteristics),
            )
            .where(ProductModel.seller_id == seller_id)
        )
        if status is not None:
            query = query.where(ProductModel.status == status.value)
        if not include_deleted:
            query = query.where(ProductModel.deleted.is_(False))
        count_result = await self._session.execute(
            select(func.count()).select_from(query.subquery())
        )
        result = await self._session.execute(query.limit(limit).offset(offset))
        return (
            [self._to_entity(m) for m in result.scalars().all()],
            count_result.scalar_one(),
        )

    async def list_by_status(
        self,
        status: ProductStatus,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ProductEntity]:
        result = await self._session.execute(
            select(ProductModel)
            .options(
                selectinload(ProductModel.images),
                selectinload(ProductModel.characteristics),
            )
            .where(ProductModel.status == status.value)
            .limit(limit)
            .offset(offset)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def save(self, product: ProductEntity) -> ProductEntity:
        model = self._to_model(product)
        await self._session.merge(model)

        # Persist images: delete existing then re-insert to keep sync with entity state
        await self._session.execute(
            select(ProductImageModel).where(ProductImageModel.product_id == product.id)
        )
        for img in product.images:
            img_model = ProductImageModel(
                id=img.id,
                product_id=product.id,
                url=img.url,
                ordering=img.ordering,
            )
            await self._session.merge(img_model)

        for char in product.characteristics:
            char_model = ProductCharacteristicModel(
                id=char.id,
                product_id=product.id,
                name=char.name,
                value=char.value,
            )
            await self._session.merge(char_model)

        await self._session.execute(
            delete(ProductFieldReportModel).where(ProductFieldReportModel.product_id == product.id)
        )
        for report in product.field_reports:
            report_model = ProductFieldReportModel(
                id=report.id,
                product_id=product.id,
                field_name=report.field_name,
                sku_id=report.sku_id,
                comment=report.comment,
            )
            await self._session.merge(report_model)

        await self._session.flush()
        return product

    async def mark_moderation_event_processed(self, idempotency_key: UUID) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self._session.execute(
            select(ModerationEventModel).where(
                ModerationEventModel.sender_service == "moderation",
                ModerationEventModel.idempotency_key == idempotency_key,
                ModerationEventModel.processed_at > cutoff,
            )
        )
        if result.scalar_one_or_none() is not None:
            return False

        try:
            async with self._session.begin_nested():
                self._session.add(
                    ModerationEventModel(
                        sender_service="moderation",
                        idempotency_key=idempotency_key,
                    )
                )
                await self._session.flush()
        except IntegrityError:
            return False
        return True

    async def get_with_skus_and_reports(
        self, product_id: UUID, *, for_update: bool = False
    ) -> ProductEntity | None:
        query = (
            select(ProductModel)
            .options(
                selectinload(ProductModel.images),
                selectinload(ProductModel.characteristics),
                selectinload(ProductModel.skus).selectinload(SkuModel.images),
                selectinload(ProductModel.skus).selectinload(
                    SkuModel.characteristics
                ),
                selectinload(ProductModel.field_reports),
            )
            .where(ProductModel.id == product_id)
        )
        if for_update:
            query = query.with_for_update()
        result = await self._session.execute(query)
        model = result.scalar_one_or_none()
        return (
            self._to_entity(model, load_skus=True, load_reports=True) if model else None
        )

    async def list_catalog_visible(
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
    ) -> tuple[list[ProductEntity], int]:
        visible_sku = exists(
            select(SkuModel.id).where(
                SkuModel.product_id == ProductModel.id,
                SkuModel.active_quantity > 0,
            )
        )
        conditions = [
            ProductModel.status == ProductStatus.MODERATED.value,
            ProductModel.deleted.is_(False),
            visible_sku,
        ]
        if ids:
            conditions.append(ProductModel.id.in_(ids))
        if category_id is not None:
            conditions.append(ProductModel.category_id == category_id)
        if seller_id is not None:
            conditions.append(ProductModel.seller_id == seller_id)
        if search:
            search_like = f"%{search}%"
            conditions.append(
                ProductModel.title.ilike(search_like)
                | ProductModel.description.ilike(search_like)
            )
        if min_price is not None:
            conditions.append(
                exists(
                    select(SkuModel.id).where(
                        SkuModel.product_id == ProductModel.id,
                        SkuModel.active_quantity > 0,
                        SkuModel.price >= min_price,
                    )
                )
            )
        if max_price is not None:
            conditions.append(
                exists(
                    select(SkuModel.id).where(
                        SkuModel.product_id == ProductModel.id,
                        SkuModel.active_quantity > 0,
                        SkuModel.price <= max_price,
                    )
                )
            )
        for char_name, char_values in (characteristic_filters or {}).items():
            conditions.append(
                exists(
                    select(ProductCharacteristicModel.id).where(
                        ProductCharacteristicModel.product_id == ProductModel.id,
                        ProductCharacteristicModel.name == char_name,
                        ProductCharacteristicModel.value.in_(char_values),
                    )
                )
            )

        count_result = await self._session.execute(
            select(func.count()).select_from(ProductModel).where(*conditions)
        )
        total_count = count_result.scalar_one()

        query = (
            select(ProductModel)
            .options(
                selectinload(ProductModel.images),
                selectinload(ProductModel.characteristics),
                selectinload(ProductModel.skus).selectinload(SkuModel.images),
                selectinload(ProductModel.skus).selectinload(
                    SkuModel.characteristics
                ),
            )
            .where(*conditions)
        )
        if sort == "price_asc":
            query = query.order_by(
                select(func.min(SkuModel.price))
                .where(
                    SkuModel.product_id == ProductModel.id, SkuModel.active_quantity > 0
                )
                .scalar_subquery()
                .asc()
            )
        elif sort == "price_desc":
            query = query.order_by(
                select(func.min(SkuModel.price))
                .where(
                    SkuModel.product_id == ProductModel.id, SkuModel.active_quantity > 0
                )
                .scalar_subquery()
                .desc()
            )
        else:
            query = query.order_by(ProductModel.created_at.desc())

        result = await self._session.execute(query.limit(limit).offset(offset))
        return [
            self._to_entity(m, load_skus=True) for m in result.scalars().all()
        ], total_count

    async def delete(self, product_id: UUID) -> None:
        result = await self._session.execute(
            select(ProductModel).where(ProductModel.id == product_id)
        )
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    def _to_entity(
        self,
        model: ProductModel,
        load_skus: bool = False,
        load_reports: bool = False,
    ) -> ProductEntity:
        from app.domain.entities.sku import SkuCharacteristicEntity, SkuEntity

        images = [
            ProductImageEntity(
                id=img.id,
                product_id=img.product_id,
                url=img.url,
                ordering=img.ordering,
                created_at=img.created_at,
            )
            for img in getattr(model, "images", [])
        ]
        characteristics = [
            CharacteristicEntity(id=c.id, name=c.name, value=c.value)
            for c in getattr(model, "characteristics", [])
        ]
        skus = []
        if load_skus:
            skus = [
                SkuEntity(
                    id=s.id,
                    product_id=s.product_id,
                    name=s.name,
                    price=s.price,
                    cost_price=s.cost_price,
                    discount=s.discount,
                    active_quantity=s.active_quantity,
                    reserved_quantity=s.reserved_quantity,
                    article=s.article,
                    images=[
                        SkuImageEntity(
                            id=image.id,
                            url=image.url,
                            ordering=image.ordering,
                            created_at=image.created_at,
                        )
                        for image in getattr(s, "images", [])
                    ] or (
                        [SkuImageEntity(url=s.image, ordering=0)] if s.image else []
                    ),
                    characteristics=[
                        SkuCharacteristicEntity(
                            id=characteristic.id,
                            name=characteristic.name,
                            value=characteristic.value,
                        )
                        for characteristic in getattr(s, "characteristics", [])
                    ],
                    is_active=s.is_active,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
                for s in getattr(model, "skus", [])
            ]
        field_reports = []
        if load_reports:
            field_reports = [
                FieldReportEntity(
                    id=r.id,
                    product_id=r.product_id,
                    field_name=r.field_name,
                    sku_id=r.sku_id,
                    comment=r.comment,
                )
                for r in getattr(model, "field_reports", [])
            ]
        return ProductEntity(
            id=model.id,
            seller_id=model.seller_id,
            category_id=model.category_id,
            title=model.title,
            description=model.description,
            slug=model.slug,
            status=ProductStatus(model.status),
            deleted=model.deleted,
            blocked=model.blocked,
            blocking_reason_id=model.blocking_reason_id,
            blocking_reason_title=model.blocking_reason_title,
            moderator_comment=model.moderator_comment,
            created_at=model.created_at,
            updated_at=model.updated_at,
            moderated_at=model.moderated_at,
            images=images,
            characteristics=characteristics,
            skus=skus,
            field_reports=field_reports,
        )

    def _to_model(self, entity: ProductEntity) -> ProductModel:
        return ProductModel(
            id=entity.id,
            seller_id=entity.seller_id,
            category_id=entity.category_id,
            title=entity.title,
            description=entity.description,
            slug=entity.slug,
            status=entity.status.value,
            deleted=entity.deleted,
            blocked=entity.blocked,
            blocking_reason_id=entity.blocking_reason_id,
            blocking_reason_title=entity.blocking_reason_title,
            moderator_comment=entity.moderator_comment,
            moderated_at=entity.moderated_at,
        )
