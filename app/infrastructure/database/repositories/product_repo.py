from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.product import CharacteristicEntity, FieldReportEntity, ProductEntity, ProductImageEntity
from app.domain.exceptions import NotFoundException
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.value_objects.product_status import ProductStatus
from app.infrastructure.database.models.product import ProductModel
from app.infrastructure.database.models.product_characteristic import ProductCharacteristicModel
from app.infrastructure.database.models.product_field_report import ProductFieldReportModel
from app.infrastructure.database.models.product_image import ProductImageModel


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

    async def get_or_raise(self, product_id: UUID) -> ProductEntity:
        entity = await self.get_by_id(product_id)
        if entity is None:
            raise NotFoundException(f"Product {product_id} not found")
        return entity

    async def list_by_seller(
        self,
        seller_id: UUID,
        status: ProductStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ProductEntity]:
        query = (
            select(ProductModel)
            .options(selectinload(ProductModel.images), selectinload(ProductModel.characteristics))
            .where(ProductModel.seller_id == seller_id)
        )
        if status is not None:
            query = query.where(ProductModel.status == status.value)
        query = query.limit(limit).offset(offset)
        result = await self._session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_by_status(
        self,
        status: ProductStatus,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ProductEntity]:
        result = await self._session.execute(
            select(ProductModel)
            .options(selectinload(ProductModel.images), selectinload(ProductModel.characteristics))
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

        await self._session.flush()
        return product

    async def get_with_skus_and_reports(self, product_id: UUID) -> ProductEntity | None:
        result = await self._session.execute(
            select(ProductModel)
            .options(
                selectinload(ProductModel.images),
                selectinload(ProductModel.characteristics),
                selectinload(ProductModel.skus),
                selectinload(ProductModel.field_reports),
            )
            .where(ProductModel.id == product_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model, load_skus=True, load_reports=True) if model else None

    async def delete(self, product_id: UUID) -> None:
        result = await self._session.execute(select(ProductModel).where(ProductModel.id == product_id))
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
                    image=s.image,
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
