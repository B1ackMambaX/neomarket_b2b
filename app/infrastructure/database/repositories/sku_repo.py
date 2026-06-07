from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.sku import SkuCharacteristicEntity, SkuEntity, SkuImageEntity
from app.domain.exceptions import NotFoundException
from app.domain.repositories.sku_repo import AbstractSkuRepository
from app.infrastructure.database.models.sku import (
    SkuCharacteristicModel,
    SkuImageModel,
    SkuModel,
)


class SQLAlchemySkuRepository(AbstractSkuRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, sku_id: UUID) -> SkuEntity | None:
        result = await self._session.execute(
            select(SkuModel)
            .options(
                selectinload(SkuModel.images),
                selectinload(SkuModel.characteristics),
            )
            .where(SkuModel.id == sku_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_id_for_update(self, sku_id: UUID) -> SkuEntity | None:
        result = await self._session.execute(
            select(SkuModel)
            .options(
                selectinload(SkuModel.images),
                selectinload(SkuModel.characteristics),
            )
            .where(SkuModel.id == sku_id)
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_many_by_ids(self, sku_ids: list[UUID]) -> list[SkuEntity]:
        if not sku_ids:
            return []
        result = await self._session.execute(
            select(SkuModel)
            .options(
                selectinload(SkuModel.images),
                selectinload(SkuModel.characteristics),
            )
            .where(SkuModel.id.in_(sku_ids))
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def get_or_raise(self, sku_id: UUID) -> SkuEntity:
        entity = await self.get_by_id(sku_id)
        if entity is None:
            raise NotFoundException(f"SKU {sku_id} not found")
        return entity

    async def list_by_product(self, product_id: UUID, only_active: bool = False) -> list[SkuEntity]:
        query = select(SkuModel).where(SkuModel.product_id == product_id)
        query = query.options(
            selectinload(SkuModel.images),
            selectinload(SkuModel.characteristics),
        )
        if only_active:
            query = query.where(SkuModel.is_active.is_(True))
        result = await self._session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def save(self, sku: SkuEntity) -> SkuEntity:
        model = await self._session.merge(self._to_model(sku))
        await self._session.flush()
        await self._session.execute(
            delete(SkuImageModel).where(SkuImageModel.sku_id == model.id)
        )
        for image in sku.images:
            await self._session.merge(
                SkuImageModel(
                    id=image.id,
                    sku_id=model.id,
                    url=image.url,
                    ordering=image.ordering,
                )
            )
        await self._session.execute(
            delete(SkuCharacteristicModel).where(
                SkuCharacteristicModel.sku_id == model.id
            )
        )
        for characteristic in sku.characteristics:
            await self._session.merge(
                SkuCharacteristicModel(
                    id=characteristic.id,
                    sku_id=model.id,
                    name=characteristic.name,
                    value=characteristic.value,
                )
            )
        await self._session.flush()
        await self._session.refresh(model, attribute_names=["images", "characteristics"])
        return self._to_entity(model)

    async def count_by_product(self, product_id: UUID) -> int:
        from sqlalchemy import func as sqlfunc
        result = await self._session.execute(
            select(sqlfunc.count()).select_from(SkuModel).where(SkuModel.product_id == product_id)
        )
        return result.scalar_one()

    async def delete(self, sku_id: UUID) -> None:
        result = await self._session.execute(select(SkuModel).where(SkuModel.id == sku_id))
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)
            await self._session.flush()

    def _to_entity(self, model: SkuModel) -> SkuEntity:
        return SkuEntity(
            id=model.id,
            product_id=model.product_id,
            name=model.name,
            price=model.price,
            cost_price=model.cost_price,
            discount=model.discount,
            reserved_quantity=model.reserved_quantity,
            active_quantity=model.active_quantity,
            article=model.article,
            images=[
                SkuImageEntity(
                    id=image.id,
                    url=image.url,
                    ordering=image.ordering,
                    created_at=image.created_at,
                )
                for image in getattr(model, "images", [])
            ] or (
                [SkuImageEntity(url=model.image, ordering=0)] if model.image else []
            ),
            characteristics=[
                SkuCharacteristicEntity(
                    id=characteristic.id,
                    name=characteristic.name,
                    value=characteristic.value,
                )
                for characteristic in getattr(model, "characteristics", [])
            ],
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: SkuEntity) -> SkuModel:
        return SkuModel(
            id=entity.id,
            product_id=entity.product_id,
            name=entity.name,
            price=entity.price,
            cost_price=entity.cost_price,
            discount=entity.discount,
            reserved_quantity=entity.reserved_quantity,
            active_quantity=entity.active_quantity,
            article=entity.article,
            image=entity.image,
            is_active=entity.is_active,
        )
