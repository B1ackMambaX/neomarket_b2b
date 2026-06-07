import json
from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timezone
from typing import cast, override
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionFactory, engine
from app.domain.entities.inventory import (
    ReservationItemResult,
    ReservationResult,
    UnreserveResult,
)
from app.domain.events import AbstractEventPublisher
from app.domain.exceptions import (
    FailedReservedItem,
    FailedStockItem,
    IdempotencyConflictException,
    InsufficientReservedException,
    InsufficientStockException,
)
from app.domain.repositories.inventory_repo import AbstractInventoryRepository
from app.infrastructure.database.models.base import Base
from app.infrastructure.database.models.product import ProductModel
from app.infrastructure.database.models.reservation import (
    ReserveOperationModel,
    SerializedInventoryItem,
    UnreserveOperationModel,
)
from app.infrastructure.database.models.seller import SellerModel
from app.infrastructure.database.models.sku import SkuModel
from app.infrastructure.external.http_b2c_event_publisher import HttpB2cEventPublisher
from app.services.inventory_service import InventoryService

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubInventoryRepo(AbstractInventoryRepository):
    def __init__(self, skus: dict[UUID, tuple[int, int]] | None = None) -> None:
        # sku_id -> (active_quantity, reserved_quantity)
        self._skus: dict[UUID, tuple[int, int]] = skus or {}
        self._operations: dict[UUID, ReservationResult] = {}
        self._unreserve_ops: dict[UUID, UnreserveResult] = {}
        self._unreserve_items: dict[UUID, list[SerializedInventoryItem]] = {}

    @override
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

        failed: list[FailedStockItem] = []
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

    @override
    async def unreserve(
        self, order_id: UUID, items: list[tuple[UUID, int]]
    ) -> UnreserveResult:
        normalized = _normalize_items(items)
        requested_items = _serialize_items(normalized)
        if order_id in self._unreserve_ops:
            if self._unreserve_items[order_id] == requested_items:
                cached = self._unreserve_ops[order_id]
                return UnreserveResult(
                    order_id=cached.order_id,
                    processed_at=cached.processed_at,
                    from_cache=True,
                )
            raise IdempotencyConflictException()

        failed: list[FailedReservedItem] = []
        for sku_id, qty in normalized:
            _, reserved = self._skus.get(sku_id, (0, 0))
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

        for sku_id, qty in normalized:
            active, reserved = self._skus.get(sku_id, (0, 0))
            self._skus[sku_id] = (active + qty, reserved - qty)

        result = UnreserveResult(
            order_id=order_id,
            processed_at=datetime.now(timezone.utc),
        )
        self._unreserve_ops[order_id] = result
        self._unreserve_items[order_id] = requested_items
        return result


class _StubEventPublisher(AbstractEventPublisher):
    def __init__(self) -> None:
        self.out_of_stock_events: list[UUID] = []

    @override
    async def publish_sku_out_of_stock(self, sku_id: UUID) -> None:
        self.out_of_stock_events.append(sku_id)

    @override
    async def publish_product_blocked(
        self, product_id: UUID, sku_ids: list[UUID], *, hard_block: bool = False
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SERVICE_KEY_HEADER = {"X-Service-Key": settings.B2C_TO_B2B_KEY}


def _normalize_items(items: list[tuple[UUID, int]]) -> list[tuple[UUID, int]]:
    quantities: dict[UUID, int] = {}
    for sku_id, qty in items:
        quantities[sku_id] = quantities.get(sku_id, 0) + qty
    return sorted(quantities.items(), key=lambda item: item[0])


def _serialize_items(items: list[tuple[UUID, int]]) -> list[SerializedInventoryItem]:
    return [{"sku_id": str(sku_id), "quantity": qty} for sku_id, qty in items]


@pytest_asyncio.fixture
async def real_db_schema() -> AsyncIterator[None]:
    try:
        async with engine.connect() as conn:
            _ = await conn.execute(text("select 1"))
    except Exception as exc:
        pytest.skip(f"Failed to connect to test DB: {exc}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _reserve(
    repo: _StubInventoryRepo,
    publisher: AbstractEventPublisher,
    payload: Mapping[str, object],
    *,
    headers: dict[str, str] | None = None,
) -> tuple[Response, _StubInventoryRepo, AbstractEventPublisher]:
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
    _ = app.dependency_overrides.pop(get_inventory_service, None)
    return response, repo, publisher


async def _unreserve(
    repo: _StubInventoryRepo,
    publisher: _StubEventPublisher,
    payload: Mapping[str, object],
) -> Response:
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
    _ = app.dependency_overrides.pop(get_inventory_service, None)
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
async def test_sku_out_of_stock_event_delivered_to_b2c(monkeypatch: pytest.MonkeyPatch):
    sku_id = uuid4()
    repo = _StubInventoryRepo({sku_id: (2, 0)})
    requests: list[Request] = []

    def handle_b2c_event(request: Request) -> Response:
        requests.append(request)
        return Response(status_code=202)

    transport = MockTransport(handle_b2c_event)

    class _B2cTestClient(AsyncClient):
        def __init__(self, timeout: float) -> None:
            super().__init__(transport=transport, timeout=timeout)

    monkeypatch.setattr(
        "app.infrastructure.external.http_b2c_event_publisher.httpx.AsyncClient",
        _B2cTestClient,
    )
    publisher = HttpB2cEventPublisher(
        url=settings.B2C_URL,
        service_key=settings.B2B_TO_B2C_KEY,
    )

    response, _, _ = await _reserve(
        repo,
        publisher,
        {
            "idempotency_key": str(uuid4()),
            "order_id": str(uuid4()),
            "items": [{"sku_id": str(sku_id), "quantity": 2}],  # takes all
        },
    )

    assert response.status_code == 200
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == f"{settings.B2C_URL}/api/v1/b2b/events"
    assert request.headers["X-Service-Key"] == settings.B2B_TO_B2C_KEY
    event = cast(dict[str, object], json.loads(request.content))
    assert event["event_type"] == "SKU_OUT_OF_STOCK"
    idempotency_key = event["idempotency_key"]
    occurred_at = event["occurred_at"]
    assert isinstance(idempotency_key, str)
    assert isinstance(occurred_at, str)
    assert UUID(idempotency_key)
    assert datetime.fromisoformat(occurred_at).tzinfo is not None
    assert event["payload"] == {"sku_id": str(sku_id)}


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


@pytest.mark.asyncio
async def test_over_unreserve_returns_409_without_phantom_stock():
    sku_id = uuid4()
    repo = _StubInventoryRepo({sku_id: (10, 2)})
    publisher = _StubEventPublisher()

    response = await _unreserve(
        repo,
        publisher,
        {
            "order_id": str(uuid4()),
            "items": [{"sku_id": str(sku_id), "quantity": 3}],
        },
    )

    assert response.status_code == 409
    data = response.json()
    assert data["code"] == "INSUFFICIENT_RESERVED"
    failed = data["details"]["failed_items"]
    assert failed == [
        {
            "sku_id": str(sku_id),
            "requested": 3,
            "reserved": 2,
            "reason": "INSUFFICIENT_RESERVED",
        }
    ]
    assert repo._skus[sku_id] == (10, 2)


@pytest.mark.asyncio
async def test_unreserve_replay_with_different_items_returns_409():
    sku_a = uuid4()
    sku_b = uuid4()
    order_id = str(uuid4())
    repo = _StubInventoryRepo({sku_a: (0, 5), sku_b: (0, 2)})
    publisher = _StubEventPublisher()

    first_response = await _unreserve(
        repo,
        publisher,
        {
            "order_id": order_id,
            "items": [{"sku_id": str(sku_a), "quantity": 5}],
        },
    )
    assert first_response.status_code == 200

    replay_response = await _unreserve(
        repo,
        publisher,
        {
            "order_id": order_id,
            "items": [{"sku_id": str(sku_b), "quantity": 2}],
        },
    )

    assert replay_response.status_code == 409
    assert replay_response.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert repo._skus[sku_a] == (5, 0)
    assert repo._skus[sku_b] == (0, 2)


@pytest.mark.asyncio
async def test_inventory_real_db_commits_reserve_and_unreserve_operations(
    real_db_schema: None,
) -> None:
    _ = real_db_schema
    from app.main import app

    seller_id = uuid4()
    product_id = uuid4()
    sku_id = uuid4()
    order_id = uuid4()
    idempotency_key = uuid4()

    async with AsyncSessionFactory() as session:
        session.add(
            SellerModel(
                id=seller_id,
                company_name="Seller",
                inn="123456789012",
                status="ACTIVE",
            )
        )
        session.add(
            ProductModel(
                id=product_id,
                seller_id=seller_id,
                category_id=uuid4(),
                title="Reserved product",
                description="Visible to buyers",
                slug="reserved-product",
                status="MODERATED",
            )
        )
        session.add(
            SkuModel(
                id=sku_id,
                product_id=product_id,
                name="Default",
                price=10000,
                cost_price=5000,
                discount=0,
                active_quantity=10,
                reserved_quantity=0,
                is_active=True,
            )
        )
        await session.commit()

    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        reserve_response = await ac.post(
            "/api/v1/inventory/reserve",
            headers=SERVICE_KEY_HEADER,
            json={
                "idempotency_key": str(idempotency_key),
                "order_id": str(order_id),
                "items": [{"sku_id": str(sku_id), "quantity": 4}],
            },
        )
        assert reserve_response.status_code == 200

        unreserve_response = await ac.post(
            "/api/v1/inventory/unreserve",
            headers=SERVICE_KEY_HEADER,
            json={
                "order_id": str(order_id),
                "items": [{"sku_id": str(sku_id), "quantity": 4}],
            },
        )
        assert unreserve_response.status_code == 200

    async with AsyncSessionFactory() as session:
        sku = await session.get(SkuModel, sku_id)
        reserve_op = await session.get(ReserveOperationModel, idempotency_key)
        unreserve_op = await session.get(UnreserveOperationModel, order_id)

    assert sku is not None
    assert sku.active_quantity == 10
    assert sku.reserved_quantity == 0
    assert reserve_op is not None
    assert unreserve_op is not None
    assert unreserve_op.items == [{"sku_id": str(sku_id), "quantity": 4}]
