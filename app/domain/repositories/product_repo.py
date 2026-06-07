from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.product import ProductEntity
from app.domain.value_objects.product_status import ProductStatus


class AbstractProductRepository(ABC):
    @abstractmethod
    async def get_by_id(self, product_id: UUID) -> ProductEntity | None: ...

    @abstractmethod
    async def get_many_by_ids(self, product_ids: list[UUID]) -> list[ProductEntity]: ...

    @abstractmethod
    async def get_by_id_for_update(self, product_id: UUID) -> ProductEntity | None: ...

    @abstractmethod
    async def get_or_raise(self, product_id: UUID) -> ProductEntity: ...

    @abstractmethod
    async def list_by_seller(
        self,
        seller_id: UUID,
        status: ProductStatus | None = None,
        include_deleted: bool = False,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ProductEntity], int]: ...

    @abstractmethod
    async def list_by_status(
        self,
        status: ProductStatus,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ProductEntity]: ...

    @abstractmethod
    async def get_with_skus_and_reports(
        self, product_id: UUID, *, for_update: bool = False
    ) -> ProductEntity | None: ...

    @abstractmethod
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
    ) -> tuple[list[ProductEntity], int]: ...

    @abstractmethod
    async def save(self, product: ProductEntity) -> ProductEntity: ...

    @abstractmethod
    async def delete(self, product_id: UUID) -> None: ...

    @abstractmethod
    async def mark_moderation_event_processed(self, idempotency_key: UUID) -> bool: ...
