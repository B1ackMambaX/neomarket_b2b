from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.sku import SkuEntity


class AbstractSkuRepository(ABC):

    @abstractmethod
    async def get_by_id(self, sku_id: UUID) -> SkuEntity | None: ...

    @abstractmethod
    async def get_or_raise(self, sku_id: UUID) -> SkuEntity: ...

    @abstractmethod
    async def list_by_product(
        self,
        product_id: UUID,
        only_active: bool = False,
    ) -> list[SkuEntity]: ...

    @abstractmethod
    async def save(self, sku: SkuEntity) -> SkuEntity: ...

    @abstractmethod
    async def delete(self, sku_id: UUID) -> None: ...
