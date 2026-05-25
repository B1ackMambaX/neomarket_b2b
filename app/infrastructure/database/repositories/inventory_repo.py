from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.inventory import ReservationItemResult, ReservationResult
from app.domain.exceptions import InsufficientStockException
from app.domain.repositories.inventory_repo import AbstractInventoryRepository
from app.infrastructure.database.models.reservation import ReserveOperationModel, UnreserveOperationModel
from app.infrastructure.database.models.sku import SkuModel


class SQLAlchemyInventoryRepository(AbstractInventoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        idempotency_key: UUID,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> ReservationResult:
        existing = await self._session.get(ReserveOperationModel, idempotency_key)
        if existing is not None:
            data = existing.result
            return ReservationResult(
                order_id=UUID(data["order_id"]),
                reserved_at=datetime.fromisoformat(data["reserved_at"]),
                items=[
                    ReservationItemResult(
                        sku_id=UUID(i["sku_id"]),
                        quantity=i["quantity"],
                        remaining_stock=i["remaining_stock"],
                    )
                    for i in data["items"]
                ],
                from_cache=True,
            )

        # Lock rows in consistent order to prevent deadlocks
        sku_ids = sorted({sku_id for sku_id, _ in items})
        rows = await self._session.execute(
            select(SkuModel)
            .where(SkuModel.id.in_(sku_ids))
            .with_for_update()
            .order_by(SkuModel.id)
        )
        sku_map = {sku.id: sku for sku in rows.scalars().all()}

        failed: list[dict] = []
        for sku_id, qty in items:
            sku = sku_map.get(sku_id)
            available = sku.active_quantity if sku else 0
            if available == 0:
                failed.append({"sku_id": sku_id, "requested": qty, "available": 0, "reason": "OUT_OF_STOCK"})
            elif available < qty:
                failed.append({"sku_id": sku_id, "requested": qty, "available": available, "reason": "INSUFFICIENT_STOCK"})

        if failed:
            raise InsufficientStockException(failed)

        reserved_at = datetime.now(timezone.utc)
        result_items: list[ReservationItemResult] = []
        out_of_stock_sku_ids: list[UUID] = []

        for sku_id, qty in items:
            sku = sku_map[sku_id]
            sku.active_quantity -= qty
            sku.reserved_quantity += qty
            remaining = sku.active_quantity
            result_items.append(ReservationItemResult(sku_id=sku_id, quantity=qty, remaining_stock=remaining))
            if remaining == 0:
                out_of_stock_sku_ids.append(sku_id)

        op = ReserveOperationModel(
            idempotency_key=idempotency_key,
            order_id=order_id,
            result={
                "order_id": str(order_id),
                "reserved_at": reserved_at.isoformat(),
                "items": [
                    {"sku_id": str(i.sku_id), "quantity": i.quantity, "remaining_stock": i.remaining_stock}
                    for i in result_items
                ],
            },
        )
        self._session.add(op)
        await self._session.flush()

        return ReservationResult(
            order_id=order_id,
            reserved_at=reserved_at,
            items=result_items,
            out_of_stock_sku_ids=out_of_stock_sku_ids,
        )

    async def unreserve(
        self,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> None:
        existing = await self._session.get(UnreserveOperationModel, order_id)
        if existing is not None:
            return

        sku_ids = sorted({sku_id for sku_id, _ in items})
        rows = await self._session.execute(
            select(SkuModel)
            .where(SkuModel.id.in_(sku_ids))
            .with_for_update()
            .order_by(SkuModel.id)
        )
        sku_map = {sku.id: sku for sku in rows.scalars().all()}

        for sku_id, qty in items:
            sku = sku_map.get(sku_id)
            if sku is not None:
                sku.active_quantity += qty
                sku.reserved_quantity = max(0, sku.reserved_quantity - qty)

        self._session.add(UnreserveOperationModel(order_id=order_id))
        await self._session.flush()
