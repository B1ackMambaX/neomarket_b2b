from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.inventory import FulfillResult, ReservationResult, UnreserveResult


class AbstractInventoryRepository(ABC):

    @abstractmethod
    async def reserve(
        self,
        idempotency_key: UUID,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> ReservationResult: ...

    @abstractmethod
    async def unreserve(
        self,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> UnreserveResult: ...

    @abstractmethod
    async def fulfill(
        self,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> FulfillResult: ...
