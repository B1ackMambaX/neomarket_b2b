from uuid import UUID

from app.domain.entities.inventory import ReservationResult, UnreserveResult
from app.domain.events import AbstractEventPublisher
from app.domain.repositories.inventory_repo import AbstractInventoryRepository


class InventoryService:
    def __init__(
        self,
        inventory_repo: AbstractInventoryRepository,
        event_publisher: AbstractEventPublisher,
    ) -> None:
        self._inventory_repo: AbstractInventoryRepository = inventory_repo
        self._event_publisher: AbstractEventPublisher = event_publisher

    async def reserve(
        self,
        idempotency_key: UUID,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> ReservationResult:
        result = await self._inventory_repo.reserve(
            idempotency_key=idempotency_key,
            order_id=order_id,
            items=items,
        )
        if not result.from_cache:
            for sku_id in result.out_of_stock_sku_ids:
                await self._event_publisher.publish_sku_out_of_stock(sku_id)
        return result

    async def unreserve(
        self,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> UnreserveResult:
        return await self._inventory_repo.unreserve(order_id=order_id, items=items)
