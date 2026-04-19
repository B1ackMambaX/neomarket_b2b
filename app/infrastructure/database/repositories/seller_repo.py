from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.seller import SellerEntity
from app.domain.exceptions import NotFoundException
from app.domain.repositories.seller_repo import AbstractSellerRepository
from app.domain.value_objects.seller_status import SellerStatus
from app.infrastructure.database.models.seller import SellerModel


class SQLAlchemySellerRepository(AbstractSellerRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, seller_id: UUID) -> SellerEntity | None:
        result = await self._session.execute(select(SellerModel).where(SellerModel.id == seller_id))
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_or_raise(self, seller_id: UUID) -> SellerEntity:
        entity = await self.get_by_id(seller_id)
        if entity is None:
            raise NotFoundException(f"Seller {seller_id} not found")
        return entity

    async def get_by_inn(self, inn: str) -> SellerEntity | None:
        result = await self._session.execute(select(SellerModel).where(SellerModel.inn == inn))
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list(self, limit: int = 20, offset: int = 0) -> list[SellerEntity]:
        result = await self._session.execute(select(SellerModel).limit(limit).offset(offset))
        return [self._to_entity(m) for m in result.scalars().all()]

    async def save(self, seller: SellerEntity) -> SellerEntity:
        await self._session.merge(self._to_model(seller))
        await self._session.flush()
        return seller

    def _to_entity(self, model: SellerModel) -> SellerEntity:
        return SellerEntity(
            id=model.id,
            company_name=model.company_name,
            inn=model.inn,
            status=SellerStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: SellerEntity) -> SellerModel:
        return SellerModel(
            id=entity.id,
            company_name=entity.company_name,
            inn=entity.inn,
            status=entity.status.value,
        )
