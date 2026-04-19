from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.sku import SkuEntity
from app.domain.exceptions import NotFoundException
from app.domain.repositories.sku_repo import AbstractSkuRepository
from app.infrastructure.database.models.sku import SkuModel


class SQLAlchemySkuRepository(AbstractSkuRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, sku_id: UUID) -> SkuEntity | None:
        result = await self._session.execute(select(SkuModel).where(SkuModel.id == sku_id))
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_or_raise(self, sku_id: UUID) -> SkuEntity:
        entity = await self.get_by_id(sku_id)
        if entity is None:
            raise NotFoundException(f"SKU {sku_id} not found")
        return entity

    async def list_by_product(self, product_id: UUID, only_active: bool = False) -> list[SkuEntity]:
        query = select(SkuModel).where(SkuModel.product_id == product_id)
        if only_active:
            query = query.where(SkuModel.is_active.is_(True))
        result = await self._session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def save(self, sku: SkuEntity) -> SkuEntity:
        model = await self._session.merge(self._to_model(sku))
        await self._session.flush()
        return self._to_entity(model)

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
            active_quantity=model.active_quantity,
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
            active_quantity=entity.active_quantity,
            is_active=entity.is_active,
        )
