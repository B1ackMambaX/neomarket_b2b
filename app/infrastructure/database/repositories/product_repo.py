from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.product import ProductEntity, ProductImageEntity, SkuEntity
from app.domain.exceptions import NotFoundException
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.value_objects.product_status import ProductStatus
from app.infrastructure.database.models.product import ProductModel
from app.infrastructure.database.models.product_image import ProductImageModel
from app.infrastructure.database.models.sku import SkuModel


class SQLAlchemyProductRepository(AbstractProductRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, product_id: UUID) -> ProductEntity | None:
        result = await self._session.execute(
            select(ProductModel)
            .options(
                selectinload(ProductModel.images),
                selectinload(ProductModel.skus),
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
        query = select(ProductModel).where(ProductModel.seller_id == seller_id)
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
            .where(ProductModel.status == status.value)
            .limit(limit)
            .offset(offset)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def save(self, product: ProductEntity) -> ProductEntity:
        await self._session.merge(self._to_model(product))
        await self._session.flush()
        return product

    async def update(
        self,
        product: ProductEntity,
        images: list[ProductImageEntity] | None = None,
    ) -> ProductEntity:
        result = await self._session.execute(
            select(ProductModel)
            .options(
                selectinload(ProductModel.images),
                selectinload(ProductModel.skus),
            )
            .where(ProductModel.id == product.id)
        )
        model = result.scalar_one_or_none()

        if model is None:
            raise NotFoundException(f"Product {product.id} not found")

        model.category_id = product.category_id
        model.title = product.title
        model.description = product.description
        model.status = product.status.value
        model.moderated_at = product.moderated_at

        if images is not None:
            model.images = [
                ProductImageModel(
                    id=image.id,
                    product_id=product.id,
                    url=image.url,
                    ordering=image.ordering,
                )
                for image in images
            ]

        await self._session.flush()
        await self._session.refresh(model)

        return await self.get_or_raise(product.id)

    async def delete(self, product_id: UUID) -> None:
        result = await self._session.execute(select(ProductModel).where(ProductModel.id == product_id))
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    def _to_entity(self, model: ProductModel) -> ProductEntity:
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
        skus = [
            SkuEntity(
                id=sku.id,
                product_id=sku.product_id,
                name=sku.name,
                price=sku.price,
                active_quantity=sku.active_quantity,
                is_active=sku.is_active,
                created_at=sku.created_at,
                updated_at=sku.updated_at,
            )
            for sku in getattr(model, "skus", [])
        ]
        return ProductEntity(
            id=model.id,
            seller_id=model.seller_id,
            category_id=model.category_id,
            title=model.title,
            description=model.description,
            status=ProductStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
            moderated_at=model.moderated_at,
            images=images,
            skus=skus,
        )

    def _to_model(self, entity: ProductEntity) -> ProductModel:
        return ProductModel(
            id=entity.id,
            seller_id=entity.seller_id,
            category_id=entity.category_id,
            title=entity.title,
            description=entity.description,
            status=entity.status.value,
            moderated_at=entity.moderated_at,
        )
