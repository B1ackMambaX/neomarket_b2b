from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.seller import SellerEntity


class AbstractSellerRepository(ABC):

    @abstractmethod
    async def get_by_id(self, seller_id: UUID) -> SellerEntity | None: ...

    @abstractmethod
    async def get_or_raise(self, seller_id: UUID) -> SellerEntity: ...

    @abstractmethod
    async def get_by_inn(self, inn: str) -> SellerEntity | None: ...

    @abstractmethod
    async def list(self, limit: int = 20, offset: int = 0) -> list[SellerEntity]: ...

    @abstractmethod
    async def save(self, seller: SellerEntity) -> SellerEntity: ...
