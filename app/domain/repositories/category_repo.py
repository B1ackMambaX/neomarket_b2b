from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.category import CategoryEntity


class AbstractCategoryRepository(ABC):
    @abstractmethod
    async def get_by_id(self, category_id: UUID) -> CategoryEntity | None: ...

    @abstractmethod
    async def get_or_raise(self, category_id: UUID) -> CategoryEntity: ...
