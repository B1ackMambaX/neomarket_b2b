from datetime import datetime, timezone
from typing import override
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.inventory import (
    FulfillResult,
    ReservationItemResult,
    ReservationResult,
    UnreserveResult,
)
from app.domain.exceptions import (
    FailedReservedItem,
    FailedStockItem,
    IdempotencyConflictException,
    InsufficientReservedException,
    InsufficientStockException,
)
from app.domain.repositories.inventory_repo import AbstractInventoryRepository
from app.infrastructure.database.models.reservation import (
    FulfillOperationModel,
    ReserveOperationModel,
    SerializedInventoryItem,
    UnreserveOperationModel,
)
from app.infrastructure.database.models.sku import SkuModel


def _normalize_items(items: list[tuple[UUID, int]]) -> list[tuple[UUID, int]]:
    quantities: dict[UUID, int] = {}
    for sku_id, qty in items:
        quantities[sku_id] = quantities.get(sku_id, 0) + qty
    return sorted(quantities.items(), key=lambda item: item[0])


def _serialize_items(items: list[tuple[UUID, int]]) -> list[SerializedInventoryItem]:
    return [{"sku_id": str(sku_id), "quantity": qty} for sku_id, qty in items]


class SQLAlchemyInventoryRepository(AbstractInventoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    @override
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

        failed: list[FailedStockItem] = []
        for sku_id, qty in items:
            sku = sku_map.get(sku_id)
            available = sku.active_quantity if sku else 0
            if available == 0:
                failed.append(
                    {
                        "sku_id": sku_id,
                        "requested": qty,
                        "available": 0,
                        "reason": "OUT_OF_STOCK",
                    }
                )
            elif available < qty:
                failed.append(
                    {
                        "sku_id": sku_id,
                        "requested": qty,
                        "available": available,
                        "reason": "INSUFFICIENT_STOCK",
                    }
                )

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
            result_items.append(
                ReservationItemResult(
                    sku_id=sku_id, quantity=qty, remaining_stock=remaining
                )
            )
            if remaining == 0:
                out_of_stock_sku_ids.append(sku_id)

        op = ReserveOperationModel(
            idempotency_key=idempotency_key,
            order_id=order_id,
            result={
                "order_id": str(order_id),
                "reserved_at": reserved_at.isoformat(),
                "items": [
                    {
                        "sku_id": str(i.sku_id),
                        "quantity": i.quantity,
                        "remaining_stock": i.remaining_stock,
                    }
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

    @override
    async def unreserve(
        self,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> UnreserveResult:
        normalized_items = _normalize_items(items)
        requested_items = _serialize_items(normalized_items)
        existing = await self._session.get(UnreserveOperationModel, order_id)
        if existing is not None:
            if existing.items == requested_items:
                return UnreserveResult(
                    order_id=order_id,
                    processed_at=existing.processed_at,
                    from_cache=True,
                )
            raise IdempotencyConflictException()

        sku_ids = [sku_id for sku_id, _ in normalized_items]
        rows = await self._session.execute(
            select(SkuModel)
            .where(SkuModel.id.in_(sku_ids))
            .with_for_update()
            .order_by(SkuModel.id)
        )
        sku_map = {sku.id: sku for sku in rows.scalars().all()}

        failed: list[FailedReservedItem] = []
        for sku_id, qty in normalized_items:
            sku = sku_map.get(sku_id)
            reserved = sku.reserved_quantity if sku else 0
            if reserved < qty:
                failed.append(
                    {
                        "sku_id": sku_id,
                        "requested": qty,
                        "reserved": reserved,
                        "reason": "INSUFFICIENT_RESERVED",
                    }
                )

        if failed:
            raise InsufficientReservedException(failed)

        processed_at = datetime.now(timezone.utc)
        for sku_id, qty in normalized_items:
            sku = sku_map[sku_id]
            sku.active_quantity += qty
            sku.reserved_quantity -= qty

        self._session.add(
            UnreserveOperationModel(
                order_id=order_id,
                items=requested_items,
                processed_at=processed_at,
            )
        )
        await self._session.flush()

        return UnreserveResult(order_id=order_id, processed_at=processed_at)

    @override
    async def fulfill(
        self,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> FulfillResult:
        normalized_items = _normalize_items(items)
        requested_items = _serialize_items(normalized_items)
        existing = await self._session.get(FulfillOperationModel, order_id)
        if existing is not None:
            return FulfillResult(
                order_id=order_id,
                processed_at=existing.processed_at,
                from_cache=True,
            )

        # Serialize concurrent retries even when their SKU sets differ.
        advisory_lock_key = order_id.int & ((1 << 63) - 1)
        _ = await self._session.execute(
            select(func.pg_advisory_xact_lock(advisory_lock_key))
        )
        existing = await self._session.get(FulfillOperationModel, order_id)
        if existing is not None:
            return FulfillResult(
                order_id=order_id,
                processed_at=existing.processed_at,
                from_cache=True,
            )

        sku_ids = [sku_id for sku_id, _ in normalized_items]
        rows = await self._session.execute(
            select(SkuModel)
            .where(SkuModel.id.in_(sku_ids))
            .with_for_update()
            .order_by(SkuModel.id)
        )
        sku_map = {sku.id: sku for sku in rows.scalars().all()}

        failed: list[FailedReservedItem] = []
        for sku_id, qty in normalized_items:
            sku = sku_map.get(sku_id)
            reserved = sku.reserved_quantity if sku else 0
            if reserved < qty:
                failed.append(
                    {
                        "sku_id": sku_id,
                        "requested": qty,
                        "reserved": reserved,
                        "reason": "INSUFFICIENT_RESERVED",
                    }
                )

        if failed:
            raise InsufficientReservedException(failed)

        processed_at = datetime.now(timezone.utc)
        for sku_id, qty in normalized_items:
            sku_map[sku_id].reserved_quantity -= qty

        self._session.add(
            FulfillOperationModel(
                order_id=order_id,
                items=requested_items,
                processed_at=processed_at,
            )
        )
        await self._session.flush()

        return FulfillResult(order_id=order_id, processed_at=processed_at)
