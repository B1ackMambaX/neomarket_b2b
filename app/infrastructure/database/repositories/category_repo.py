from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.category import CategoryEntity
from app.domain.exceptions import ValidationException
from app.domain.repositories.category_repo import AbstractCategoryRepository
from app.infrastructure.database.models.category import CategoryModel


class SQLAlchemyCategoryRepository(AbstractCategoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, category_id: UUID) -> CategoryEntity | None:
        result = await self._session.execute(
            select(CategoryModel).where(CategoryModel.id == category_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_or_raise(self, category_id: UUID) -> CategoryEntity:
        entity = await self.get_by_id(category_id)
        if entity is None:
            raise ValidationException("Category not found")
        return entity

    def _to_entity(self, model: CategoryModel) -> CategoryEntity:
        return CategoryEntity(
            id=model.id,
            name=model.name,
            parent_id=model.parent_id,
            is_active=model.is_active,
            created_at=model.created_at,
        )
