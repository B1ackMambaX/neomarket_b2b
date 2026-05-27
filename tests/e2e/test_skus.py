"""
E2E tests for POST /api/v1/skus.
Most tests use dependency overrides; ORM persistence regression uses the test DB.
"""
# pyright: reportAny=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false, reportUnusedFunction=false

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from typing_extensions import override

from app.core.config import settings
from app.core.database import AsyncSessionFactory, engine
from app.core.security import create_access_token
from app.domain.entities.product import ProductEntity
from app.domain.entities.sku import SkuEntity
from app.domain.exceptions import NotFoundException
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.sku_repo import AbstractSkuRepository
from app.domain.value_objects.product_status import ProductStatus
from app.infrastructure.database.models import (
    ProductModel,
    SellerModel,
    SkuImageModel,
    SkuModel,
)
from app.infrastructure.database.models.base import Base
from app.infrastructure.external.moderation_client import AbstractModerationClient
from app.services.sku_service import SkuService

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubSkuRepo(AbstractSkuRepository):
    def __init__(self, existing_count: int = 0) -> None:
        self._count: int = existing_count
        self.saved: list[SkuEntity] = []

    @override
    async def get_by_id(self, sku_id: UUID) -> SkuEntity | None:
        return None

    @override
    async def get_or_raise(self, sku_id: UUID) -> SkuEntity:
        raise NotFoundException(f"SKU {sku_id} not found")

    @override
    async def list_by_product(
        self, product_id: UUID, only_active: bool = False
    ) -> list[SkuEntity]:
        return []

    @override
    async def count_by_product(self, product_id: UUID) -> int:
        return self._count

    @override
    async def save(self, sku: SkuEntity) -> SkuEntity:
        self.saved.append(sku)
        return sku

    @override
    async def delete(self, sku_id: UUID) -> None:
        pass


class _StubProductRepo(AbstractProductRepository):
    def __init__(self, product: ProductEntity | None) -> None:
        self._product: ProductEntity | None = product
        self.saved: list[ProductEntity] = []

    @override
    async def get_by_id(self, product_id: UUID) -> ProductEntity | None:
        return self._product

    @override
    async def get_by_id_for_update(self, product_id: UUID) -> ProductEntity | None:
        return self._product

    @override
    async def get_or_raise(self, product_id: UUID) -> ProductEntity:
        if self._product is None:
            raise NotFoundException("Product not found")
        return self._product

    @override
    async def get_with_skus_and_reports(self, product_id: UUID) -> ProductEntity | None:
        return self._product

    @override
    async def list_by_seller(
        self,
        seller_id: UUID,
        status: ProductStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ProductEntity]:
        return []

    @override
    async def list_by_status(
        self, status: ProductStatus, limit: int = 20, offset: int = 0
    ) -> list[ProductEntity]:
        return []

    @override
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
    ) -> tuple[list[ProductEntity], int]:
        return [], 0

    @override
    async def save(self, product: ProductEntity) -> ProductEntity:
        self.saved.append(product)
        return product

    @override
    async def delete(self, product_id: UUID) -> None:
        pass

    @override
    async def mark_moderation_event_processed(self, idempotency_key: UUID) -> bool:
        return True


class _FakeModerationClient(AbstractModerationClient):
    def __init__(self) -> None:
        self.events: list[ProductEntity] = []

    @override
    async def send_product_created(self, product: ProductEntity) -> None:
        self.events.append(product)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seller_id() -> UUID:
    return uuid4()


@pytest.fixture
def valid_token(seller_id: UUID) -> str:
    return create_access_token({"sub": str(seller_id)}, settings.SECRET_KEY)


def _make_product(
    seller_id: UUID, status: ProductStatus = ProductStatus.CREATED
) -> ProductEntity:
    return ProductEntity(
        id=uuid4(),
        seller_id=seller_id,
        category_id=uuid4(),
        title="Test Product",
        slug="test-product",
        status=status,
    )


def _make_service(
    seller_id: UUID,
    product: ProductEntity | None = None,
    existing_sku_count: int = 0,
    moderation_client: _FakeModerationClient | None = None,
) -> tuple[SkuService, _FakeModerationClient, _StubSkuRepo, _StubProductRepo]:
    mod_client = moderation_client or _FakeModerationClient()
    sku_repo = _StubSkuRepo(existing_count=existing_sku_count)
    product_repo = _StubProductRepo(product=product or _make_product(seller_id))
    service = SkuService(
        sku_repo=sku_repo,
        product_repo=product_repo,
        moderation_client=mod_client,
    )
    return service, mod_client, sku_repo, product_repo


_VALID_PAYLOAD = {
    "product_id": str(uuid4()),  # overridden per test
    "name": "256GB Black",
    "price": 12999000,
    "cost_price": 9500000,
    "discount": 0,
    "images": [{"url": "https://cdn.example.com/sku.jpg", "ordering": 0}],
    "characteristics": [{"name": "Цвет", "value": "Чёрный"}],
}


@pytest_asyncio.fixture
async def _client_and_deps(
    seller_id: UUID,
) -> AsyncIterator[
    tuple[
        AsyncClient, SkuService, _FakeModerationClient, _StubSkuRepo, _StubProductRepo
    ]
]:
    """Yields (AsyncClient, service, mod_client, sku_repo, product_repo)."""
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id)
    service, mod_client, sku_repo, product_repo = _make_service(
        seller_id, product=product
    )

    app.dependency_overrides[get_sku_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, service, mod_client, sku_repo, product_repo
    _ = app.dependency_overrides.pop(get_sku_service, None)


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_sku_transitions_product_to_on_moderation(
    seller_id: UUID, valid_token: str
) -> None:
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id, status=ProductStatus.CREATED)
    service, _, sku_repo, product_repo = _make_service(
        seller_id, product=product, existing_sku_count=0
    )
    app.dependency_overrides[get_sku_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {**_VALID_PAYLOAD, "product_id": str(product.id)}
        response = await ac.post(
            "/api/v1/skus",
            json=payload,
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    _ = app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 201
    # product was saved after status transition
    assert len(product_repo.saved) == 1
    assert product_repo.saved[0].status == ProductStatus.ON_MODERATION
    assert len(sku_repo.saved[0].images) == 1
    assert sku_repo.saved[0].images[0].url == "https://cdn.example.com/sku.jpg"


@pytest.mark.asyncio
async def test_first_sku_emits_created_event_to_moderation(
    seller_id: UUID, valid_token: str
) -> None:
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id, status=ProductStatus.CREATED)
    mod_client = _FakeModerationClient()
    service, _, _1, _2 = _make_service(
        seller_id, product=product, existing_sku_count=0, moderation_client=mod_client
    )
    app.dependency_overrides[get_sku_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {**_VALID_PAYLOAD, "product_id": str(product.id)}
        response = await ac.post(
            "/api/v1/skus",
            json=payload,
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    _ = app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 201
    # asyncio.create_task schedules the coroutine; give event loop a tick
    import asyncio

    await asyncio.sleep(0)
    assert len(mod_client.events) == 1
    assert mod_client.events[0].id == product.id
    assert mod_client.events[0].seller_id == seller_id


@pytest.mark.asyncio
async def test_invalid_token_returns_401_contract_error(
    _client_and_deps: tuple[
        AsyncClient,
        SkuService,
        _FakeModerationClient,
        _StubSkuRepo,
        _StubProductRepo,
    ],
) -> None:
    ac, _service, _mod_client, _sku_repo, product_repo = _client_and_deps
    product = await product_repo.get_or_raise(uuid4())

    payload = {**_VALID_PAYLOAD, "product_id": str(product.id)}
    response = await ac.post(
        "/api/v1/skus",
        json=payload,
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"code": "UNAUTHORIZED", "message": "Invalid token"}


@pytest.mark.asyncio
async def test_second_sku_no_state_change(seller_id: UUID, valid_token: str) -> None:
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id, status=ProductStatus.ON_MODERATION)
    mod_client = _FakeModerationClient()
    service, _, _2, product_repo = _make_service(
        seller_id, product=product, existing_sku_count=1, moderation_client=mod_client
    )
    app.dependency_overrides[get_sku_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {**_VALID_PAYLOAD, "product_id": str(product.id)}
        response = await ac.post(
            "/api/v1/skus",
            json=payload,
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    _ = app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 201
    # no product save, no event
    assert len(product_repo.saved) == 0

    import asyncio

    await asyncio.sleep(0)
    assert len(mod_client.events) == 0


@pytest.mark.asyncio
async def test_add_sku_to_hard_blocked_returns_403(
    seller_id: UUID, valid_token: str
) -> None:
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id, status=ProductStatus.HARD_BLOCKED)
    service, _, _, _ = _make_service(seller_id, product=product)
    app.dependency_overrides[get_sku_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {**_VALID_PAYLOAD, "product_id": str(product.id)}
        response = await ac.post(
            "/api/v1/skus",
            json=payload,
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    _ = app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_missing_image_returns_400(seller_id: UUID, valid_token: str) -> None:
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id)
    service, _, _, _ = _make_service(seller_id, product=product)
    app.dependency_overrides[get_sku_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {**_VALID_PAYLOAD, "product_id": str(product.id), "images": []}
        response = await ac.post(
            "/api/v1/skus",
            json=payload,
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    _ = app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 400
    assert "image" in response.json().get("message", "").lower()


@pytest.mark.asyncio
async def test_other_seller_product_returns_not_owner(
    seller_id: UUID, valid_token: str
) -> None:
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(uuid4())
    service, _, _, _ = _make_service(seller_id, product=product)
    app.dependency_overrides[get_sku_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {**_VALID_PAYLOAD, "product_id": str(product.id)}
        response = await ac.post(
            "/api/v1/skus",
            json=payload,
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    _ = app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 403
    assert response.json()["code"] == "NOT_OWNER"


@pytest.mark.asyncio
async def test_create_sku_response_preserves_all_images(
    seller_id: UUID, valid_token: str
) -> None:
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id, status=ProductStatus.ON_MODERATION)
    service, _, _, _ = _make_service(seller_id, product=product, existing_sku_count=1)
    app.dependency_overrides[get_sku_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            **_VALID_PAYLOAD,
            "product_id": str(product.id),
            "images": [
                {"url": "https://cdn.example.com/first.jpg", "ordering": 1},
                {"url": "https://cdn.example.com/cover.jpg", "ordering": 0},
            ],
        }
        response = await ac.post(
            "/api/v1/skus",
            json=payload,
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    _ = app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 201
    body = response.json()
    assert [image["url"] for image in body["images"]] == [
        "https://cdn.example.com/cover.jpg",
        "https://cdn.example.com/first.jpg",
    ]
    assert all(image["id"] for image in body["images"])


@pytest.mark.asyncio
async def test_create_sku_persists_real_orm_path(
    real_db_schema: None, seller_id: UUID, valid_token: str
) -> None:
    from app.core.dependencies import get_moderation_client
    from app.main import app

    _ = real_db_schema
    product_id = uuid4()
    category_id = uuid4()
    mod_client = _FakeModerationClient()

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
                category_id=category_id,
                title="Real ORM Product",
                slug="real-orm-product",
                status=ProductStatus.CREATED.value,
            )
        )
        await session.commit()

    app.dependency_overrides[get_moderation_client] = lambda: mod_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/skus",
            json={
                **_VALID_PAYLOAD,
                "product_id": str(product_id),
                "images": [
                    {"url": "https://cdn.example.com/one.jpg", "ordering": 0},
                    {"url": "https://cdn.example.com/two.jpg", "ordering": 1},
                ],
            },
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    _ = app.dependency_overrides.pop(get_moderation_client, None)

    assert response.status_code == 201
    body = response.json()
    assert [image["url"] for image in body["images"]] == [
        "https://cdn.example.com/one.jpg",
        "https://cdn.example.com/two.jpg",
    ]

    async with AsyncSessionFactory() as session:
        sku = await session.get(SkuModel, UUID(body["id"]))
        product = await session.get(ProductModel, product_id)
        images = (
            (
                await session.execute(
                    select(SkuImageModel)
                    .where(SkuImageModel.sku_id == UUID(body["id"]))
                    .order_by(SkuImageModel.ordering)
                )
            )
            .scalars()
            .all()
        )

    assert sku is not None
    assert product is not None
    assert product.status == ProductStatus.ON_MODERATION.value
    assert [image.url for image in images] == [
        "https://cdn.example.com/one.jpg",
        "https://cdn.example.com/two.jpg",
    ]
