from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.product import ProductEntity
from app.domain.value_objects.product_status import ProductStatus


class AbstractProductRepository(ABC):

    @abstractmethod
    async def get_by_id(self, product_id: UUID) -> ProductEntity | None: ...

    @abstractmethod
    async def get_or_raise(self, product_id: UUID) -> ProductEntity: ...

    @abstractmethod
    async def list_by_seller(
        self,
        seller_id: UUID,
        status: ProductStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ProductEntity]: ...

    @abstractmethod
    async def list_by_status(
        self,
        status: ProductStatus,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ProductEntity]: ...

    @abstractmethod
    async def get_with_skus_and_reports(self, product_id: UUID) -> ProductEntity | None: ...

    @abstractmethod
    async def save(self, product: ProductEntity) -> ProductEntity: ...

    @abstractmethod
    async def delete(self, product_id: UUID) -> None: ...
