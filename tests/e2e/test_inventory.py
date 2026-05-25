from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.domain.entities.inventory import ReservationItemResult, ReservationResult
from app.domain.events import AbstractEventPublisher
from app.domain.exceptions import InsufficientStockException
from app.domain.repositories.inventory_repo import AbstractInventoryRepository
from app.services.inventory_service import InventoryService

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubInventoryRepo(AbstractInventoryRepository):
    def __init__(self, skus: dict[UUID, tuple[int, int]] | None = None) -> None:
        # sku_id -> (active_quantity, reserved_quantity)
        self._skus: dict[UUID, tuple[int, int]] = skus or {}
        self._operations: dict[UUID, ReservationResult] = {}
        self._unreserve_ops: set[UUID] = set()

    async def reserve(
        self,
        idempotency_key: UUID,
        order_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> ReservationResult:
        if idempotency_key in self._operations:
            cached = self._operations[idempotency_key]
            return ReservationResult(
                order_id=cached.order_id,
                reserved_at=cached.reserved_at,
                items=cached.items,
                out_of_stock_sku_ids=cached.out_of_stock_sku_ids,
                from_cache=True,
            )

        failed: list[dict] = []
        for sku_id, qty in items:
            active, _ = self._skus.get(sku_id, (0, 0))
            if active == 0:
                failed.append(
                    {
                        "sku_id": sku_id,
                        "requested": qty,
                        "available": 0,
                        "reason": "OUT_OF_STOCK",
                    }
                )
            elif active < qty:
                failed.append(
                    {
                        "sku_id": sku_id,
                        "requested": qty,
                        "available": active,
                        "reason": "INSUFFICIENT_STOCK",
                    }
                )

        if failed:
            raise InsufficientStockException(failed)

        from datetime import datetime, timezone

        result_items: list[ReservationItemResult] = []
        out_of_stock: list[UUID] = []

        for sku_id, qty in items:
            active, reserved = self._skus[sku_id]
            new_active = active - qty
            self._skus[sku_id] = (new_active, reserved + qty)
            result_items.append(
                ReservationItemResult(
                    sku_id=sku_id, quantity=qty, remaining_stock=new_active
                )
            )
            if new_active == 0:
                out_of_stock.append(sku_id)

        result = ReservationResult(
            order_id=order_id,
            reserved_at=datetime.now(timezone.utc),
            items=result_items,
            out_of_stock_sku_ids=out_of_stock,
        )
        self._operations[idempotency_key] = result
        return result

    async def unreserve(self, order_id: UUID, items: list[tuple[UUID, int]]) -> None:
        if order_id in self._unreserve_ops:
            return
        for sku_id, qty in items:
            active, reserved = self._skus.get(sku_id, (0, 0))
            self._skus[sku_id] = (active + qty, max(0, reserved - qty))
        self._unreserve_ops.add(order_id)


class _StubEventPublisher(AbstractEventPublisher):
    def __init__(self) -> None:
        self.out_of_stock_events: list[UUID] = []

    async def publish_sku_out_of_stock(self, sku_id: UUID) -> None:
        self.out_of_stock_events.append(sku_id)

    async def publish_product_blocked(
        self, product_id: UUID, sku_ids: list[UUID], *, hard_block: bool = False
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SERVICE_KEY_HEADER = {"X-Service-Key": settings.B2C_TO_B2B_KEY}


async def _reserve(
    repo: _StubInventoryRepo,
    publisher: _StubEventPublisher,
    payload: dict,
    *,
    headers: dict | None = None,
) -> tuple[object, _StubInventoryRepo, _StubEventPublisher]:
    from app.core.dependencies import get_inventory_service
    from app.main import app

    app.dependency_overrides[get_inventory_service] = lambda: InventoryService(
        inventory_repo=repo, event_publisher=publisher
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/inventory/reserve",
            headers=headers if headers is not None else SERVICE_KEY_HEADER,
            json=payload,
        )
    app.dependency_overrides.pop(get_inventory_service, None)
    return response, repo, publisher


async def _unreserve(
    repo: _StubInventoryRepo,
    publisher: _StubEventPublisher,
    payload: dict,
) -> object:
    from app.core.dependencies import get_inventory_service
    from app.main import app

    app.dependency_overrides[get_inventory_service] = lambda: InventoryService(
        inventory_repo=repo, event_publisher=publisher
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/inventory/unreserve",
            headers=SERVICE_KEY_HEADER,
            json=payload,
        )
    app.dependency_overrides.pop(get_inventory_service, None)
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reserve_all_skus_succeeds():
    sku_a = uuid4()
    sku_b = uuid4()
    repo = _StubInventoryRepo({sku_a: (10, 0), sku_b: (5, 0)})
    publisher = _StubEventPublisher()

    response, repo, _ = await _reserve(
        repo,
        publisher,
        {
            "idempotency_key": str(uuid4()),
            "order_id": str(uuid4()),
            "items": [
                {"sku_id": str(sku_a), "quantity": 3},
                {"sku_id": str(sku_b), "quantity": 2},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["reserved"] is True
    assert data["status"] == "RESERVED"
    assert len(data["items"]) == 2

    active_a, reserved_a = repo._skus[sku_a]
    active_b, reserved_b = repo._skus[sku_b]
    assert active_a == 7 and reserved_a == 3
    assert active_b == 3 and reserved_b == 2


@pytest.mark.asyncio
async def test_partial_insufficient_stock_returns_409_all_rollback():
    sku_ok = uuid4()
    sku_short = uuid4()
    repo = _StubInventoryRepo({sku_ok: (10, 0), sku_short: (1, 0)})
    publisher = _StubEventPublisher()

    response, repo, _ = await _reserve(
        repo,
        publisher,
        {
            "idempotency_key": str(uuid4()),
            "order_id": str(uuid4()),
            "items": [
                {"sku_id": str(sku_ok), "quantity": 5},
                {"sku_id": str(sku_short), "quantity": 5},  # only 1 available
            ],
        },
    )

    assert response.status_code == 409
    data = response.json()
    assert data["code"] == "INSUFFICIENT_STOCK"
    assert "message" in data
    failed = data["details"]["failed_items"]
    assert len(failed) == 1
    assert failed[0]["sku_id"] == str(sku_short)
    assert failed[0]["reason"] == "INSUFFICIENT_STOCK"

    # All-or-nothing: sku_ok must not have been changed
    assert repo._skus[sku_ok] == (10, 0)
    assert repo._skus[sku_short] == (1, 0)


@pytest.mark.asyncio
async def test_idempotent_reserve_returns_200_without_double_deduction():
    sku_id = uuid4()
    repo = _StubInventoryRepo({sku_id: (10, 0)})
    publisher = _StubEventPublisher()
    idempotency_key = str(uuid4())
    order_id = str(uuid4())
    payload = {
        "idempotency_key": idempotency_key,
        "order_id": order_id,
        "items": [{"sku_id": str(sku_id), "quantity": 3}],
    }

    response1, repo, _ = await _reserve(repo, publisher, payload)
    assert response1.status_code == 200

    response2, repo, _ = await _reserve(repo, publisher, payload)
    assert response2.status_code == 200

    # Quantity must reflect only one reservation, not two
    active, reserved = repo._skus[sku_id]
    assert active == 7 and reserved == 3


@pytest.mark.asyncio
async def test_sku_out_of_stock_event_emitted():
    sku_id = uuid4()
    repo = _StubInventoryRepo({sku_id: (2, 0)})
    publisher = _StubEventPublisher()

    response, _, publisher = await _reserve(
        repo,
        publisher,
        {
            "idempotency_key": str(uuid4()),
            "order_id": str(uuid4()),
            "items": [{"sku_id": str(sku_id), "quantity": 2}],  # takes all
        },
    )

    assert response.status_code == 200
    assert sku_id in publisher.out_of_stock_events


@pytest.mark.asyncio
async def test_unreserve_restores_quantities():
    sku_a = uuid4()
    sku_b = uuid4()
    # Simulate already-reserved state
    repo = _StubInventoryRepo({sku_a: (0, 3), sku_b: (5, 2)})
    publisher = _StubEventPublisher()

    response = await _unreserve(
        repo,
        publisher,
        {
            "order_id": str(uuid4()),
            "items": [
                {"sku_id": str(sku_a), "quantity": 3},
                {"sku_id": str(sku_b), "quantity": 2},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UNRESERVED"

    active_a, reserved_a = repo._skus[sku_a]
    active_b, reserved_b = repo._skus[sku_b]
    assert active_a == 3 and reserved_a == 0
    assert active_b == 7 and reserved_b == 0


@pytest.mark.asyncio
async def test_idempotent_unreserve_no_double_restore():
    sku_id = uuid4()
    order_id = str(uuid4())
    # Already-reserved state
    repo = _StubInventoryRepo({sku_id: (0, 5)})
    publisher = _StubEventPublisher()
    payload = {
        "order_id": order_id,
        "items": [{"sku_id": str(sku_id), "quantity": 5}],
    }

    response1 = await _unreserve(repo, publisher, payload)
    assert response1.status_code == 200

    response2 = await _unreserve(repo, publisher, payload)
    assert response2.status_code == 200

    # Invariant must hold: double call must not double-restore
    active, reserved = repo._skus[sku_id]
    assert active == 5 and reserved == 0
