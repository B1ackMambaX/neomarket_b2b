"""
E2E tests for POST /api/v1/products and GET /api/v1/products/{id}.
Dependencies are overridden so no real DB is required.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.security import create_access_token
from app.domain.entities.category import CategoryEntity
from app.domain.entities.product import (
    CharacteristicEntity,
    FieldReportEntity,
    ProductEntity,
    ProductImageEntity,
)
from app.domain.entities.seller import SellerEntity
from app.domain.entities.sku import SkuEntity
from app.domain.exceptions import NotFoundException, ValidationException
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
    async def get_with_skus_and_reports(self, product_id): return None
    async def list_by_seller(self, seller_id, status=None, limit=20, offset=0): return []
    async def list_by_status(self, status, limit=20, offset=0): return []
    async def list_catalog_visible(
        self, ids=None, category_id=None, seller_id=None, search=None, min_price=None, max_price=None,
        sort="created_desc", limit=20, offset=0
    ): return [], 0
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
async def test_missing_category_returns_422(client, valid_token):
    payload = {k: v for k, v in _VALID_PAYLOAD.items() if k != "category_id"}
    response = await client.post(
        "/api/v1/products",
        json=payload,
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 422
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


# ---------------------------------------------------------------------------
# GET /api/v1/products/{product_id} — DoD tests (B2B-5)
# ---------------------------------------------------------------------------


def _make_moderated_product(seller_id: UUID) -> ProductEntity:
    product = ProductEntity(
        id=uuid4(),
        seller_id=seller_id,
        category_id=uuid4(),
        title="iPhone 15 Pro",
        description="Flagship",
        slug="iphone-15-pro",
        status=ProductStatus.MODERATED,
        deleted=False,
        blocked=False,
    )
    product.images.append(
        ProductImageEntity(product_id=product.id, url="https://cdn.example.com/img.jpg", ordering=0)
    )
    product.skus.append(
        SkuEntity(
            product_id=product.id,
            name="256GB Black",
            price=12999000,
            cost_price=9500000,
            discount=0,
            reserved_quantity=2,
            active_quantity=10,
        )
    )
    return product


def _make_blocked_product(seller_id: UUID) -> ProductEntity:
    product_id = uuid4()
    sku_id = uuid4()
    product = ProductEntity(
        id=product_id,
        seller_id=seller_id,
        category_id=uuid4(),
        title="Levi's 501",
        description="Jeans",
        slug="levis-501",
        status=ProductStatus.BLOCKED,
        deleted=False,
        blocked=True,
        blocking_reason_id=uuid4(),
        blocking_reason_title="Описание не соответствует товару",
        moderator_comment="Несоответствие описания и фотографий",
    )
    product.skus.append(
        SkuEntity(
            id=sku_id,
            product_id=product_id,
            name="Размер 32",
            price=899000,
            cost_price=450000,
            discount=0,
            active_quantity=0,
            reserved_quantity=0,
        )
    )
    product.field_reports.extend([
        FieldReportEntity(
            product_id=product_id,
            field_name="description",
            comment="В описании указан материал 'натуральная кожа', на фото -- синтетика",
        ),
        FieldReportEntity(
            product_id=product_id,
            field_name="sku_image",
            sku_id=sku_id,
            comment="Фото SKU не соответствует указанному цвету",
        ),
    ])
    return product


class _DetailProductRepo(AbstractProductRepository):
    def __init__(self, product: ProductEntity | None):
        self._product = product

    async def get_by_id(self, product_id): return None
    async def get_or_raise(self, product_id):
        if self._product is None:
            raise NotFoundException("Product not found")
        return self._product
    async def get_with_skus_and_reports(self, product_id):
        if self._product and self._product.id == product_id:
            return self._product
        return None
    async def list_by_seller(self, seller_id, status=None, limit=20, offset=0): return []
    async def list_by_status(self, status, limit=20, offset=0): return []
    async def list_catalog_visible(
        self, ids=None, category_id=None, seller_id=None, search=None, min_price=None, max_price=None,
        sort="created_desc", limit=20, offset=0
    ): return [], 0
    async def save(self, product): return product
    async def delete(self, product_id): pass


def _make_detail_service(seller_id: UUID, product: ProductEntity | None) -> ProductService:
    category = CategoryEntity(id=product.category_id if product else uuid4(), name="Electronics")

    class _CategoryRepo(AbstractCategoryRepository):
        async def get_by_id(self, cid):
            return category if cid == category.id else None
        async def get_or_raise(self, cid):
            return category

    return ProductService(
        product_repo=_DetailProductRepo(product),
        seller_repo=_StubSellerRepo(seller_id),
        category_repo=_CategoryRepo(),
    )


@pytest.mark.asyncio
async def test_get_moderated_product_returns_full_payload(seller_id, valid_token):
    from app.core.dependencies import get_product_service
    from app.main import app

    product = _make_moderated_product(seller_id)
    service = _make_detail_service(seller_id, product)
    app.dependency_overrides[get_product_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            f"/api/v1/products/{product.id}",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    app.dependency_overrides.pop(get_product_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(product.id)
    assert data["status"] == "MODERATED"
    assert data["blocked"] is False
    assert data["blocking_reason"] is None
    assert data["field_reports"] == []
    assert len(data["skus"]) == 1
    sku = data["skus"][0]
    assert sku["cost_price"] == 9500000
    assert sku["reserved_quantity"] == 2
    assert "category" in data
    assert data["category"]["name"] == "Electronics"


@pytest.mark.asyncio
async def test_get_blocked_product_returns_blocking_reason_and_field_reports(seller_id, valid_token):
    from app.core.dependencies import get_product_service
    from app.main import app

    product = _make_blocked_product(seller_id)
    service = _make_detail_service(seller_id, product)
    app.dependency_overrides[get_product_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            f"/api/v1/products/{product.id}",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    app.dependency_overrides.pop(get_product_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "BLOCKED"
    assert data["blocked"] is True
    blocking_reason = data["blocking_reason"]
    assert blocking_reason is not None
    assert blocking_reason["title"] == "Описание не соответствует товару"
    assert blocking_reason["comment"] == "Несоответствие описания и фотографий"
    assert len(data["field_reports"]) == 2
    field_names = {r["field_name"] for r in data["field_reports"]}
    assert "description" in field_names
    assert "sku_image" in field_names


@pytest.mark.asyncio
async def test_get_others_product_returns_404(valid_token):
    from app.core.dependencies import get_product_service
    from app.main import app

    other_seller_id = uuid4()
    product = _make_moderated_product(other_seller_id)

    requester_id = uuid4()
    requester_token = create_access_token({"sub": str(requester_id)}, settings.SECRET_KEY)

    service = _make_detail_service(requester_id, product)
    app.dependency_overrides[get_product_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            f"/api/v1/products/{product.id}",
            headers={"Authorization": f"Bearer {requester_token}"},
        )
    app.dependency_overrides.pop(get_product_service, None)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_product_via_service_key_bypasses_idor(valid_token):
    from app.core.config import settings
    from app.core.dependencies import get_product_service
    from app.main import app

    other_seller_id = uuid4()
    product = _make_moderated_product(other_seller_id)
    service = _make_detail_service(other_seller_id, product)
    app.dependency_overrides[get_product_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            f"/api/v1/products/{product.id}",
            headers={"X-Service-Key": settings.B2B_TO_MOD_KEY},
        )
    app.dependency_overrides.pop(get_product_service, None)

    assert response.status_code == 200
    assert response.json()["id"] == str(product.id)


@pytest.mark.asyncio
async def test_get_nonexistent_product_returns_404(seller_id, valid_token):
    from app.core.dependencies import get_product_service
    from app.main import app

    service = _make_detail_service(seller_id, product=None)
    app.dependency_overrides[get_product_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            f"/api/v1/products/{uuid4()}",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    app.dependency_overrides.pop(get_product_service, None)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# /api/v1/public/products — DoD tests (B2B-7 catalog for B2C)
# ---------------------------------------------------------------------------


class _CatalogProductRepo(AbstractProductRepository):
    def __init__(self, products: list[ProductEntity]):
        self._products = products

    async def get_by_id(self, product_id): return None
    async def get_or_raise(self, product_id): raise NotImplementedError
    async def get_with_skus_and_reports(self, product_id): return None
    async def list_by_seller(self, seller_id, status=None, limit=20, offset=0): return []
    async def list_by_status(self, status, limit=20, offset=0): return []

    async def list_catalog_visible(
        self,
        ids=None,
        category_id=None,
        seller_id=None,
        search=None,
        min_price=None,
        max_price=None,
        sort="created_desc",
        limit=20,
        offset=0,
    ):
        selected = []
        ids_set = set(ids or [])
        for product in self._products:
            if ids is not None and product.id not in ids_set:
                continue
            if category_id is not None and product.category_id != category_id:
                continue
            if seller_id is not None and product.seller_id != seller_id:
                continue
            if product.status != ProductStatus.MODERATED:
                continue
            if product.deleted:
                continue
            if not any(sku.active_quantity > 0 for sku in product.skus):
                continue
            if min_price is not None and not any(
                sku.active_quantity > 0 and sku.price >= min_price for sku in product.skus
            ):
                continue
            if max_price is not None and not any(
                sku.active_quantity > 0 and sku.price <= max_price for sku in product.skus
            ):
                continue
            selected.append(product)
        total_count = len(selected)
        return selected[offset : offset + limit], total_count

    async def save(self, product): return product
    async def delete(self, product_id): pass


def _make_catalog_product(
    seller_id: UUID,
    *,
    status: ProductStatus = ProductStatus.MODERATED,
    deleted: bool = False,
    active_quantity: int = 10,
) -> ProductEntity:
    product = ProductEntity(
        id=uuid4(),
        seller_id=seller_id,
        category_id=uuid4(),
        title="Catalog Product",
        description="Visible to buyers",
        slug="catalog-product",
        status=status,
        deleted=deleted,
        blocked=status in {ProductStatus.BLOCKED, ProductStatus.HARD_BLOCKED},
    )
    product.images.append(
        ProductImageEntity(product_id=product.id, url="https://cdn.example.com/catalog.jpg", ordering=0)
    )
    product.characteristics.append(CharacteristicEntity(name="Brand", value="Neo"))
    product.skus.append(
        SkuEntity(
            product_id=product.id,
            name="Default",
            price=10000,
            cost_price=5000,
            discount=0,
            active_quantity=active_quantity,
            reserved_quantity=3,
            image="https://cdn.example.com/sku.jpg",
        )
    )
    return product


def _make_catalog_service(products: list[ProductEntity]) -> ProductService:
    categories = {
        product.category_id: CategoryEntity(id=product.category_id, name="Catalog")
        for product in products
    }

    class _CategoryRepo(AbstractCategoryRepository):
        async def get_by_id(self, cid):
            return categories.get(cid)
        async def get_or_raise(self, cid):
            return categories[cid]

    seller_id = products[0].seller_id if products else uuid4()
    return ProductService(
        product_repo=_CatalogProductRepo(products),
        seller_repo=_StubSellerRepo(seller_id),
        category_repo=_CategoryRepo(),
    )


async def _get_catalog(products: list[ProductEntity], *, headers=None, params=None):
    from app.core.dependencies import get_product_service
    from app.main import app

    app.dependency_overrides[get_product_service] = lambda: _make_catalog_service(products)
    transport = ASGITransport(app=app)
    request_headers = {"X-Service-Key": settings.B2C_TO_B2B_KEY} if headers is None else headers
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/public/products",
            headers=request_headers,
            params=params,
        )
    app.dependency_overrides.pop(get_product_service, None)
    return response


@pytest.mark.asyncio
async def test_catalog_returns_moderated_in_stock_products(seller_id):
    visible = _make_catalog_product(seller_id)
    created = _make_catalog_product(seller_id, status=ProductStatus.CREATED)
    deleted = _make_catalog_product(seller_id, deleted=True)
    out_of_stock = _make_catalog_product(seller_id, active_quantity=0)

    response = await _get_catalog([visible, created, deleted, out_of_stock])

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert [item["id"] for item in data["items"]] == [str(visible.id)]
    assert data["items"][0]["min_price"] == 10000


@pytest.mark.asyncio
async def test_catalog_excludes_hard_blocked(seller_id):
    visible = _make_catalog_product(seller_id)
    hard_blocked = _make_catalog_product(seller_id, status=ProductStatus.HARD_BLOCKED)

    response = await _get_catalog([visible, hard_blocked])

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(visible.id)]


@pytest.mark.asyncio
async def test_catalog_missing_service_key_returns_401(seller_id):
    visible = _make_catalog_product(seller_id)

    response = await _get_catalog([visible], headers={})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_catalog_response_has_no_cost_price(seller_id):
    visible = _make_catalog_product(seller_id)

    response = await _post_catalog_batch([visible], [visible.id])

    assert response.status_code == 200
    sku = response.json()[0]["skus"][0]
    assert "cost_price" not in sku
    assert "reserved_quantity" not in sku


@pytest.mark.asyncio
async def test_batch_ids_returns_visible_subset(seller_id):
    visible = _make_catalog_product(seller_id)
    hidden = _make_catalog_product(seller_id, status=ProductStatus.HARD_BLOCKED)
    missing_id = uuid4()

    response = await _post_catalog_batch([visible, hidden], [visible.id, hidden.id, missing_id])

    assert response.status_code == 200
    data = response.json()
    assert [item["id"] for item in data] == [str(visible.id)]


async def _post_catalog_batch(products: list[ProductEntity], product_ids: list[UUID], *, headers=None):
    from app.core.dependencies import get_product_service
    from app.main import app

    app.dependency_overrides[get_product_service] = lambda: _make_catalog_service(products)
    transport = ASGITransport(app=app)
    request_headers = {"X-Service-Key": settings.B2C_TO_B2B_KEY} if headers is None else headers
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/public/products/batch",
            headers=request_headers,
            json={"product_ids": [str(product_id) for product_id in product_ids]},
        )
    app.dependency_overrides.pop(get_product_service, None)
    return response
