# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from collections.abc import AsyncIterator
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.security import create_access_token
from app.domain.entities.invoice import InvoiceEntity
from app.domain.entities.product import ProductEntity
from app.domain.entities.sku import SkuEntity
from app.domain.repositories.invoice_repo import AbstractInvoiceRepository
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.sku_repo import AbstractSkuRepository
from app.domain.value_objects.product_status import ProductStatus
from app.services.invoice_service import InvoiceService


class _InvoiceRepo:
    def __init__(self) -> None:
        self.saved: list[InvoiceEntity] = []

    async def save(self, invoice: InvoiceEntity) -> InvoiceEntity:
        self.saved.append(invoice)
        return invoice


class _SkuRepo:
    def __init__(self, sku: SkuEntity) -> None:
        self._sku: SkuEntity = sku

    async def get_many_by_ids(self, sku_ids: list[UUID]) -> list[SkuEntity]:
        return [self._sku] if self._sku.id in sku_ids else []


class _ProductRepo:
    def __init__(self, product: ProductEntity) -> None:
        self._product: ProductEntity = product

    async def get_many_by_ids(self, product_ids: list[UUID]) -> list[ProductEntity]:
        return [self._product] if self._product.id in product_ids else []


def _make_service(
    seller_id: UUID,
    *,
    product_status: ProductStatus = ProductStatus.MODERATED,
    product_seller_id: UUID | None = None,
) -> tuple[InvoiceService, _InvoiceRepo, SkuEntity]:
    product = ProductEntity(
        seller_id=product_seller_id or seller_id,
        category_id=uuid4(),
        title="Test product",
        status=product_status,
    )
    sku = SkuEntity(
        product_id=product.id,
        name="256GB Black",
        price=129_990_00,
        cost_price=95_000_00,
    )
    invoice_repo = _InvoiceRepo()
    service = InvoiceService(
        invoice_repo=cast(AbstractInvoiceRepository, cast(object, invoice_repo)),
        sku_repo=cast(AbstractSkuRepository, cast(object, _SkuRepo(sku))),
        product_repo=cast(
            AbstractProductRepository,
            cast(object, _ProductRepo(product)),
        ),
    )
    return service, invoice_repo, sku


@pytest_asyncio.fixture
async def invoice_client(
    request: pytest.FixtureRequest,
) -> AsyncIterator[tuple[AsyncClient, _InvoiceRepo, SkuEntity, UUID]]:
    from app.core.dependencies import get_invoice_service
    from app.main import app

    seller_id = uuid4()
    params = cast(dict[str, object], getattr(request, "param", {}))
    service, invoice_repo, sku = _make_service(
        seller_id,
        product_status=cast(
            ProductStatus,
            params.get("product_status", ProductStatus.MODERATED),
        ),
        product_seller_id=cast(UUID | None, params.get("product_seller_id")),
    )
    token = create_access_token({"sub": str(seller_id)}, settings.SECRET_KEY)

    app.dependency_overrides[get_invoice_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {token}"
        yield client, invoice_repo, sku, seller_id
    _ = app.dependency_overrides.pop(get_invoice_service, None)


@pytest.mark.asyncio
async def test_create_invoice_with_moderated_sku_returns_201(
    invoice_client: tuple[AsyncClient, _InvoiceRepo, SkuEntity, UUID],
) -> None:
    client, invoice_repo, sku, seller_id = invoice_client

    response = await client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(sku.id), "quantity": 10}]},
    )

    assert response.status_code == 201
    assert len(invoice_repo.saved) == 1
    assert response.json() == {
        "id": str(invoice_repo.saved[0].id),
        "seller_id": str(seller_id),
        "status": "CREATED",
        "items": [
            {
                "id": str(invoice_repo.saved[0].items[0].id),
                "sku_id": str(sku.id),
                "quantity": 10,
                "accepted_quantity": 0,
            }
        ],
        "created_at": invoice_repo.saved[0].created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": invoice_repo.saved[0].updated_at.isoformat().replace("+00:00", "Z"),
        "accepted_at": None,
        "accepted_by": None,
    }


@pytest.mark.asyncio
async def test_empty_items_returns_400(
    invoice_client: tuple[AsyncClient, _InvoiceRepo, SkuEntity, UUID],
) -> None:
    client, invoice_repo, _, _ = invoice_client

    response = await client.post("/api/v1/invoices", json={"items": []})

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "At least one item is required",
    }
    assert invoice_repo.saved == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invoice_client",
    [{"product_status": ProductStatus.CREATED}],
    indirect=True,
)
async def test_non_moderated_sku_returns_400(
    invoice_client: tuple[AsyncClient, _InvoiceRepo, SkuEntity, UUID],
) -> None:
    client, invoice_repo, sku, _ = invoice_client

    response = await client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(sku.id), "quantity": 1}]},
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "Invoice can only be created for MODERATED products",
    }
    assert invoice_repo.saved == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invoice_client",
    [{"product_seller_id": uuid4()}],
    indirect=True,
)
async def test_others_sku_returns_403(
    invoice_client: tuple[AsyncClient, _InvoiceRepo, SkuEntity, UUID],
) -> None:
    client, invoice_repo, sku, _ = invoice_client

    response = await client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(sku.id), "quantity": 1}]},
    )

    assert response.status_code == 403
    assert response.json() == {
        "code": "NOT_OWNER",
        "message": "One or more SKUs do not belong to the authenticated seller",
    }
    assert invoice_repo.saved == []


@pytest.mark.asyncio
async def test_non_positive_quantity_returns_422(
    invoice_client: tuple[AsyncClient, _InvoiceRepo, SkuEntity, UUID],
) -> None:
    client, invoice_repo, sku, _ = invoice_client

    response = await client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(sku.id), "quantity": 0}]},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"
    assert "greater than 0" in body["message"]
    assert invoice_repo.saved == []


@pytest.mark.asyncio
async def test_missing_sku_returns_404(
    invoice_client: tuple[AsyncClient, _InvoiceRepo, SkuEntity, UUID],
) -> None:
    client, invoice_repo, _, _ = invoice_client

    response = await client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(uuid4()), "quantity": 1}]},
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "SKU not found",
    }
    assert invoice_repo.saved == []
