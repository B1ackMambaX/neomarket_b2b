"""
E2E tests for POST /api/v1/skus.
All dependencies are overridden — no real DB or Moderation service required.
"""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.security import create_access_token
from app.domain.entities.product import ProductEntity
from app.domain.entities.sku import SkuEntity
from app.domain.exceptions import NotFoundException
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.sku_repo import AbstractSkuRepository
from app.domain.value_objects.product_status import ProductStatus
from app.infrastructure.external.moderation_client import AbstractModerationClient
from app.services.sku_service import SkuService

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubSkuRepo(AbstractSkuRepository):
    def __init__(self, existing_count: int = 0):
        self._count = existing_count
        self.saved: list[SkuEntity] = []

    async def get_by_id(self, sku_id: UUID) -> SkuEntity | None:
        return None

    async def get_or_raise(self, sku_id: UUID) -> SkuEntity:
        raise NotFoundException(f"SKU {sku_id} not found")

    async def list_by_product(
        self, product_id: UUID, only_active: bool = False
    ) -> list[SkuEntity]:
        return []

    async def count_by_product(self, product_id: UUID) -> int:
        return self._count

    async def save(self, sku: SkuEntity) -> SkuEntity:
        self.saved.append(sku)
        return sku

    async def delete(self, sku_id: UUID) -> None:
        pass


class _StubProductRepo(AbstractProductRepository):
    def __init__(self, product: ProductEntity | None):
        self._product = product
        self.saved: list[ProductEntity] = []

    async def get_by_id(self, product_id: UUID) -> ProductEntity | None:
        return self._product

    async def get_or_raise(self, product_id: UUID) -> ProductEntity:
        if self._product is None:
            raise NotFoundException("Product not found")
        return self._product

    async def get_with_skus_and_reports(self, product_id: UUID) -> ProductEntity | None:
        return self._product

    async def list_by_seller(self, seller_id, status=None, limit=20, offset=0):
        return []

    async def list_by_status(self, status, limit=20, offset=0):
        return []

    async def save(self, product: ProductEntity) -> ProductEntity:
        self.saved.append(product)
        return product

    async def delete(self, product_id: UUID) -> None:
        pass


class _FakeModerationClient(AbstractModerationClient):
    def __init__(self):
        self.events: list[ProductEntity] = []

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
    moderation_client: AbstractModerationClient | None = None,
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
async def _client_and_deps(seller_id):
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
    app.dependency_overrides.pop(get_sku_service, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_sku_transitions_product_to_on_moderation(seller_id, valid_token):
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id, status=ProductStatus.CREATED)
    service, mod_client, sku_repo, product_repo = _make_service(
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
    app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 201
    # product was saved after status transition
    assert len(product_repo.saved) == 1
    assert product_repo.saved[0].status == ProductStatus.ON_MODERATION


@pytest.mark.asyncio
async def test_first_sku_emits_created_event_to_moderation(seller_id, valid_token):
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id, status=ProductStatus.CREATED)
    mod_client = _FakeModerationClient()
    service, _, sku_repo, product_repo = _make_service(
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
    app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 201
    # asyncio.create_task schedules the coroutine; give event loop a tick
    import asyncio

    await asyncio.sleep(0)
    assert len(mod_client.events) == 1
    assert mod_client.events[0].id == product.id
    assert mod_client.events[0].seller_id == seller_id


@pytest.mark.asyncio
async def test_invalid_token_returns_401_contract_error(_client_and_deps):
    ac, _, _, _, product_repo = _client_and_deps
    product = product_repo._product
    assert product is not None

    payload = {**_VALID_PAYLOAD, "product_id": str(product.id)}
    response = await ac.post(
        "/api/v1/skus",
        json=payload,
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"code": "UNAUTHORIZED", "message": "Invalid token"}


@pytest.mark.asyncio
async def test_second_sku_no_state_change(seller_id, valid_token):
    from app.core.dependencies import get_sku_service
    from app.main import app

    product = _make_product(seller_id, status=ProductStatus.ON_MODERATION)
    mod_client = _FakeModerationClient()
    service, _, sku_repo, product_repo = _make_service(
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
    app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 201
    # no product save, no event
    assert len(product_repo.saved) == 0

    import asyncio

    await asyncio.sleep(0)
    assert len(mod_client.events) == 0


@pytest.mark.asyncio
async def test_add_sku_to_hard_blocked_returns_403(seller_id, valid_token):
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
    app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_missing_image_returns_400(seller_id, valid_token):
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
    app.dependency_overrides.pop(get_sku_service, None)

    assert response.status_code == 400
    assert "image" in response.json().get("message", "").lower()
