"""
E2E tests for POST /api/v1/products.
Dependencies are overridden so no real DB is required.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from uuid import uuid4

from app.core.config import settings
from app.core.security import create_access_token
from app.domain.entities.category import CategoryEntity
from app.domain.entities.product import CharacteristicEntity, ProductEntity, ProductImageEntity
from app.domain.entities.seller import SellerEntity
from app.domain.exceptions import ValidationException
from app.domain.repositories.category_repo import AbstractCategoryRepository
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.seller_repo import AbstractSellerRepository
from app.domain.value_objects.product_status import ProductStatus
from app.services.product_service import ProductService


# ---------------------------------------------------------------------------
# Stub repositories
# ---------------------------------------------------------------------------

class _StubProductRepo(AbstractProductRepository):
    async def get_by_id(self, product_id): return None
    async def get_or_raise(self, product_id): raise NotImplementedError
    async def list_by_seller(self, seller_id, status=None, limit=20, offset=0): return []
    async def list_by_status(self, status, limit=20, offset=0): return []
    async def save(self, product: ProductEntity) -> ProductEntity: return product
    async def delete(self, product_id): pass


class _StubSellerRepo(AbstractSellerRepository):
    def __init__(self, seller_id):
        self._seller_id = seller_id

    async def get_by_id(self, sid):
        return SellerEntity(id=sid, company_name="Test Co", inn="1234567890")

    async def get_or_raise(self, sid):
        return await self.get_by_id(sid)

    async def get_by_inn(self, inn): return None
    async def list(self, limit=20, offset=0): return []
    async def save(self, seller): return seller


class _StubCategoryRepo(AbstractCategoryRepository):
    def __init__(self, exists: bool = True):
        self._exists = exists

    async def get_by_id(self, category_id):
        if not self._exists:
            return None
        return CategoryEntity(id=category_id, name="Electronics")

    async def get_or_raise(self, category_id):
        entity = await self.get_by_id(category_id)
        if entity is None:
            raise ValidationException("Category not found")
        return entity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seller_id():
    return uuid4()


@pytest.fixture
def valid_token(seller_id):
    return create_access_token({"sub": str(seller_id)}, settings.SECRET_KEY)


def _make_service(seller_id, category_exists: bool = True) -> ProductService:
    return ProductService(
        product_repo=_StubProductRepo(),
        seller_repo=_StubSellerRepo(seller_id),
        category_repo=_StubCategoryRepo(exists=category_exists),
    )


@pytest_asyncio.fixture
async def client(seller_id):
    from app.core.dependencies import get_product_service
    from app.main import app

    app.dependency_overrides[get_product_service] = lambda: _make_service(seller_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_no_category(seller_id):
    from app.core.dependencies import get_product_service
    from app.main import app

    app.dependency_overrides[get_product_service] = lambda: _make_service(seller_id, category_exists=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


_VALID_PAYLOAD = {
    "title": "Ноутбук Pro",
    "description": "Мощный ноутбук для работы",
    "category_id": str(uuid4()),
    "images": [{"url": "https://cdn.example.com/laptop.jpg", "ordering": 0}],
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_product_returns_201_with_created_status(client, valid_token):
    response = await client.post(
        "/api/v1/products",
        json=_VALID_PAYLOAD,
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == ProductStatus.CREATED
    assert data["skus"] == []
    assert "id" in data


@pytest.mark.asyncio
async def test_seller_id_taken_from_jwt(client, seller_id, valid_token):
    response = await client.post(
        "/api/v1/products",
        json=_VALID_PAYLOAD,
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 201
    assert response.json()["seller_id"] == str(seller_id)


@pytest.mark.asyncio
async def test_missing_images_returns_400(client, valid_token):
    payload = {**_VALID_PAYLOAD, "images": []}
    response = await client.post(
        "/api/v1/products",
        json=payload,
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 400
    body = response.json()
    assert "image" in body.get("message", "").lower()


@pytest.mark.asyncio
async def test_missing_category_returns_400(client, valid_token):
    payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "category_id"}
    response = await client.post(
        "/api/v1/products",
        json=payload,
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body.get("code") == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_invalid_category_id_returns_400(client_no_category, valid_token):
    response = await client_no_category.post(
        "/api/v1/products",
        json=_VALID_PAYLOAD,
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 400
    body = response.json()
    assert "category" in body.get("message", "").lower()
