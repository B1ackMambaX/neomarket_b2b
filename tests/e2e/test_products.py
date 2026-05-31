"""
E2E tests for POST /api/v1/products and GET /api/v1/products/{id}.
Most tests use dependency overrides; real ORM regressions use the test DB.
"""
# pyright: reportAny=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false

from collections.abc import AsyncIterator
from typing import override
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import event, text

from app.core.config import settings
from app.core.database import AsyncSessionFactory, engine
from app.core.security import create_access_token
from app.domain.entities.category import CategoryEntity
from app.domain.entities.product import (
    CharacteristicEntity,
    FieldReportEntity,
    ProductEntity,
    ProductImageEntity,
)
from app.domain.entities.seller import SellerEntity
from app.domain.entities.sku import SkuEntity, SkuImageEntity
from app.domain.exceptions import NotFoundException, ValidationException
from app.domain.repositories.category_repo import AbstractCategoryRepository
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.seller_repo import AbstractSellerRepository
from app.domain.value_objects.product_status import ProductStatus
from app.infrastructure.database.models import (
    CategoryModel,
    ProductModel,
    SellerModel,
    SkuModel,
)
from app.infrastructure.database.models.base import Base
from app.services.product_service import ProductService

# ---------------------------------------------------------------------------
# Stub repositories
# ---------------------------------------------------------------------------


class _ProductRepoStub(AbstractProductRepository):
    def __init__(
        self,
        *,
        product: ProductEntity | None = None,
        products: list[ProductEntity] | None = None,
    ) -> None:
        self._products: list[ProductEntity] = (
            products if products is not None else ([] if product is None else [product])
        )
        self.saved: list[ProductEntity] = []

    def _find(self, product_id: UUID) -> ProductEntity | None:
        return next(
            (product for product in self._products if product.id == product_id),
            None,
        )

    @override
    async def get_by_id(self, product_id: UUID) -> ProductEntity | None:
        return self._find(product_id)

    @override
    async def get_by_id_for_update(self, product_id: UUID) -> ProductEntity | None:
        return self._find(product_id)

    @override
    async def get_or_raise(self, product_id: UUID) -> ProductEntity:
        product = self._find(product_id)
        if product is None:
            raise NotFoundException("Product not found")
        return product

    @override
    async def get_with_skus_and_reports(self, product_id: UUID) -> ProductEntity | None:
        return self._find(product_id)

    @override
    async def list_by_seller(
        self,
        seller_id: UUID,
        status: ProductStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ProductEntity]:
        selected = [
            product
            for product in self._products
            if product.seller_id == seller_id
            and (status is None or product.status == status)
        ]
        return selected[offset : offset + limit]

    @override
    async def list_by_status(
        self, status: ProductStatus, limit: int = 20, offset: int = 0
    ) -> list[ProductEntity]:
        selected = [product for product in self._products if product.status == status]
        return selected[offset : offset + limit]

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
        selected: list[ProductEntity] = []
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
            product_skus = _product_skus(product)
            if not any(sku.active_quantity > 0 for sku in product_skus):
                continue
            if min_price is not None and not any(
                sku.active_quantity > 0 and sku.price >= min_price
                for sku in product_skus
            ):
                continue
            if max_price is not None and not any(
                sku.active_quantity > 0 and sku.price <= max_price
                for sku in product_skus
            ):
                continue
            if characteristic_filters:
                char_map: dict[str, list[str]] = {}
                for characteristic in product.characteristics:
                    char_map.setdefault(characteristic.name, []).append(
                        characteristic.value
                    )
                if not all(
                    any(value in char_map.get(name, []) for value in values)
                    for name, values in characteristic_filters.items()
                ):
                    continue
            selected.append(product)
        total_count = len(selected)
        return selected[offset : offset + limit], total_count

    @override
    async def save(self, product: ProductEntity) -> ProductEntity:
        self.saved.append(product)
        if self._find(product.id) is None:
            self._products.append(product)
        return product

    @override
    async def delete(self, product_id: UUID) -> None:
        pass

    @override
    async def mark_moderation_event_processed(self, idempotency_key: UUID) -> bool:
        return True


class _StubSellerRepo(AbstractSellerRepository):
    def __init__(self, seller_id: UUID):
        self._seller_id: UUID = seller_id

    @override
    async def get_by_id(self, seller_id: UUID):
        return SellerEntity(id=seller_id, company_name="Test Co", inn="1234567890")

    @override
    async def get_or_raise(self, seller_id: UUID):
        return await self.get_by_id(seller_id)

    @override
    async def get_by_inn(self, inn: str):
        return None

    @override
    async def list(self, limit: int = 20, offset: int = 0) -> list[SellerEntity]:
        return []

    @override
    async def save(self, seller: SellerEntity):
        return seller


class _StubCategoryRepo(AbstractCategoryRepository):
    def __init__(self, exists: bool = True):
        self._exists: bool = exists

    @override
    async def get_by_id(self, category_id: UUID):
        if not self._exists:
            return None
        return CategoryEntity(id=category_id, name="Electronics")

    @override
    async def get_or_raise(self, category_id: UUID):
        entity = await self.get_by_id(category_id)
        if entity is None:
            raise ValidationException("Category not found")
        return entity


def _product_skus(product: ProductEntity) -> list[SkuEntity]:
    return product.skus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seller_id() -> UUID:
    return uuid4()


@pytest.fixture
def valid_token(seller_id: UUID) -> str:
    return create_access_token({"sub": str(seller_id)}, settings.SECRET_KEY)


def _make_service(seller_id: UUID, category_exists: bool = True) -> ProductService:
    return ProductService(
        product_repo=_ProductRepoStub(),
        seller_repo=_StubSellerRepo(seller_id),
        category_repo=_StubCategoryRepo(exists=category_exists),
    )


@pytest_asyncio.fixture
async def client(seller_id: UUID) -> AsyncIterator[AsyncClient]:
    from app.core.dependencies import get_product_service
    from app.main import app

    app.dependency_overrides[get_product_service] = lambda: _make_service(seller_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_no_category(seller_id: UUID) -> AsyncIterator[AsyncClient]:
    from app.core.dependencies import get_product_service
    from app.main import app

    app.dependency_overrides[get_product_service] = lambda: _make_service(
        seller_id, category_exists=False
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def real_db_schema() -> AsyncIterator[None]:
    try:
        async with engine.connect() as conn:
            _ = await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Error connecting to test DB: {exc}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


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
async def test_create_product_returns_201_with_created_status(
    client: AsyncClient, valid_token: str
) -> None:
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
async def test_seller_id_taken_from_jwt(
    client: AsyncClient, seller_id: UUID, valid_token: str
) -> None:
    response = await client.post(
        "/api/v1/products",
        json=_VALID_PAYLOAD,
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 201
    assert response.json()["seller_id"] == str(seller_id)


@pytest.mark.asyncio
async def test_invalid_token_returns_401_contract_error(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/products",
        json=_VALID_PAYLOAD,
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401
    assert response.json() == {"code": "UNAUTHORIZED", "message": "Invalid token"}


@pytest.mark.asyncio
async def test_missing_images_returns_400(
    client: AsyncClient, valid_token: str
) -> None:
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
async def test_missing_category_returns_422(
    client: AsyncClient, valid_token: str
) -> None:
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
async def test_invalid_category_id_returns_400(
    client_no_category: AsyncClient, valid_token: str
) -> None:
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
        ProductImageEntity(
            product_id=product.id, url="https://cdn.example.com/img.jpg", ordering=0
        )
    )
    _product_skus(product).append(
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
    _product_skus(product).append(
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
    product.field_reports.extend(
        [
            FieldReportEntity(
                product_id=product_id,
                field_name="description",
                comment="В описании указан материал 'кожа', на фото -- синтетика",
            ),
            FieldReportEntity(
                product_id=product_id,
                field_name="sku_image",
                sku_id=sku_id,
                comment="Фото SKU не соответствует указанному цвету",
            ),
        ]
    )
    return product


def _make_detail_service(
    seller_id: UUID, product: ProductEntity | None
) -> ProductService:
    category = CategoryEntity(
        id=product.category_id if product else uuid4(), name="Electronics"
    )

    class _CategoryRepo(AbstractCategoryRepository):
        @override
        async def get_by_id(self, category_id: UUID) -> CategoryEntity | None:
            return category if category_id == category.id else None

        @override
        async def get_or_raise(self, category_id: UUID) -> CategoryEntity:
            return category

    return ProductService(
        product_repo=_ProductRepoStub(product=product),
        seller_repo=_StubSellerRepo(seller_id),
        category_repo=_CategoryRepo(),
    )


@pytest.mark.asyncio
async def test_get_moderated_product_returns_full_payload(
    seller_id: UUID, valid_token: str
) -> None:
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
    _ = app.dependency_overrides.pop(get_product_service, None)

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
async def test_get_blocked_product_returns_blocking_reason_and_field_reports(
    seller_id: UUID, valid_token: str
) -> None:
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
    _ = app.dependency_overrides.pop(get_product_service, None)

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
async def test_get_others_product_returns_404() -> None:
    from app.core.dependencies import get_product_service
    from app.main import app

    other_seller_id = uuid4()
    product = _make_moderated_product(other_seller_id)

    requester_id = uuid4()
    requester_token = create_access_token(
        {"sub": str(requester_id)}, settings.SECRET_KEY
    )

    service = _make_detail_service(requester_id, product)
    app.dependency_overrides[get_product_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            f"/api/v1/products/{product.id}",
            headers={"Authorization": f"Bearer {requester_token}"},
        )
    _ = app.dependency_overrides.pop(get_product_service, None)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_product_via_service_key_bypasses_idor() -> None:
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
    _ = app.dependency_overrides.pop(get_product_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(product.id)
    assert "deleted" not in data
    assert "blocking_reason" not in data
    assert "field_reports" not in data
    sku = data["skus"][0]
    assert "cost_price" not in sku
    assert "reserved_quantity" not in sku


@pytest.mark.asyncio
async def test_get_nonexistent_product_returns_404(
    seller_id: UUID, valid_token: str
) -> None:
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
    _ = app.dependency_overrides.pop(get_product_service, None)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# /api/v1/public/products — DoD tests (B2B-7 catalog for B2C)
# ---------------------------------------------------------------------------


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
        ProductImageEntity(
            product_id=product.id, url="https://cdn.example.com/catalog.jpg", ordering=0
        )
    )
    product.characteristics.append(CharacteristicEntity(name="Brand", value="Neo"))
    _product_skus(product).append(
        SkuEntity(
            product_id=product.id,
            name="Default",
            price=10000,
            cost_price=5000,
            discount=0,
            active_quantity=active_quantity,
            reserved_quantity=3,
            images=[SkuImageEntity(url="https://cdn.example.com/sku.jpg")],
        )
    )
    return product


def _make_catalog_service(products: list[ProductEntity]) -> ProductService:
    categories = {
        product.category_id: CategoryEntity(id=product.category_id, name="Catalog")
        for product in products
    }

    class _CategoryRepo(AbstractCategoryRepository):
        @override
        async def get_by_id(self, category_id: UUID) -> CategoryEntity | None:
            return categories.get(category_id)

        @override
        async def get_or_raise(self, category_id: UUID) -> CategoryEntity:
            return categories[category_id]

    seller_id = products[0].seller_id if products else uuid4()
    return ProductService(
        product_repo=_ProductRepoStub(products=products),
        seller_repo=_StubSellerRepo(seller_id),
        category_repo=_CategoryRepo(),
    )


@pytest.mark.asyncio
async def test_catalog_real_db_does_not_query_categories_per_product(
    real_db_schema: None, seller_id: UUID
) -> None:
    _ = real_db_schema
    from app.main import app

    product_ids = [uuid4() for _ in range(3)]
    category_ids = [uuid4() for _ in product_ids]

    async with AsyncSessionFactory() as session:
        session.add(
            SellerModel(
                id=seller_id,
                company_name="Seller",
                inn="123456789012",
                status="ACTIVE",
            )
        )
        for index, (product_id, category_id) in enumerate(
            zip(product_ids, category_ids, strict=True)
        ):
            session.add(CategoryModel(id=category_id, name=f"Category {index}"))
            session.add(
                ProductModel(
                    id=product_id,
                    seller_id=seller_id,
                    category_id=category_id,
                    title=f"Catalog Product {index}",
                    description="Visible to buyers",
                    slug=f"catalog-product-{index}",
                    status=ProductStatus.MODERATED.value,
                )
            )
            session.add(
                SkuModel(
                    product_id=product_id,
                    name=f"Default {index}",
                    price=10000 + index,
                    cost_price=5000,
                    discount=0,
                    active_quantity=10,
                    reserved_quantity=0,
                    is_active=True,
                )
            )
        await session.commit()

    category_selects = 0

    def count_category_selects(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal category_selects
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("select") and " from categories" in normalized:
            category_selects += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_category_selects)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/public/products",
                headers={"X-Service-Key": settings.B2C_TO_B2B_KEY},
                params={"limit": 100},
            )
    finally:
        event.remove(
            engine.sync_engine,
            "before_cursor_execute",
            count_category_selects,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 3
    assert {item["id"] for item in data["items"]} == {
        str(product_id) for product_id in product_ids
    }
    assert category_selects == 0


async def _get_catalog(
    products: list[ProductEntity],
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str | list[str]] | None = None,
) -> Response:
    from app.core.dependencies import get_product_service
    from app.main import app

    app.dependency_overrides[get_product_service] = lambda: _make_catalog_service(
        products
    )
    transport = ASGITransport(app=app)
    request_headers = (
        {"X-Service-Key": settings.B2C_TO_B2B_KEY} if headers is None else headers
    )
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/public/products",
            headers=request_headers,
            params=params,
        )
    _ = app.dependency_overrides.pop(get_product_service, None)
    return response


@pytest.mark.asyncio
async def test_catalog_returns_moderated_in_stock_products(
    seller_id: UUID,
) -> None:
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
async def test_catalog_excludes_hard_blocked(seller_id: UUID) -> None:
    visible = _make_catalog_product(seller_id)
    hard_blocked = _make_catalog_product(seller_id, status=ProductStatus.HARD_BLOCKED)

    response = await _get_catalog([visible, hard_blocked])

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(visible.id)]


@pytest.mark.asyncio
async def test_catalog_missing_service_key_returns_401(seller_id: UUID) -> None:
    visible = _make_catalog_product(seller_id)

    response = await _get_catalog([visible], headers={})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_catalog_response_has_no_cost_price(seller_id: UUID) -> None:
    visible = _make_catalog_product(seller_id)

    response = await _post_catalog_batch([visible], [visible.id])

    assert response.status_code == 200
    sku = response.json()[0]["skus"][0]
    assert "cost_price" not in sku
    assert "reserved_quantity" not in sku


@pytest.mark.asyncio
async def test_batch_ids_returns_visible_subset(seller_id: UUID) -> None:
    visible = _make_catalog_product(seller_id)
    hidden = _make_catalog_product(seller_id, status=ProductStatus.HARD_BLOCKED)
    missing_id = uuid4()

    response = await _post_catalog_batch(
        [visible, hidden], [visible.id, hidden.id, missing_id]
    )

    assert response.status_code == 200
    data = response.json()
    assert [item["id"] for item in data] == [str(visible.id)]


async def _post_catalog_batch(
    products: list[ProductEntity],
    product_ids: list[UUID],
    *,
    headers: dict[str, str] | None = None,
) -> Response:
    from app.core.dependencies import get_product_service
    from app.main import app

    app.dependency_overrides[get_product_service] = lambda: _make_catalog_service(
        products
    )
    transport = ASGITransport(app=app)
    request_headers = (
        {"X-Service-Key": settings.B2C_TO_B2B_KEY} if headers is None else headers
    )
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/public/products/batch",
            headers=request_headers,
            json={"product_ids": [str(product_id) for product_id in product_ids]},
        )
    _ = app.dependency_overrides.pop(get_product_service, None)
    return response


@pytest.mark.asyncio
async def test_catalog_characteristic_filter_returns_matching_products(
    seller_id: UUID,
) -> None:
    apple = _make_catalog_product(seller_id)
    apple.characteristics.clear()
    apple.characteristics.append(CharacteristicEntity(name="brand", value="apple"))

    samsung = _make_catalog_product(seller_id)
    samsung.characteristics.clear()
    samsung.characteristics.append(CharacteristicEntity(name="brand", value="samsung"))

    other = _make_catalog_product(seller_id)
    other.characteristics.clear()
    other.characteristics.append(CharacteristicEntity(name="brand", value="xiaomi"))

    response = await _get_catalog(
        [apple, samsung, other],
        params={"filters[brand]": ["apple", "samsung"]},
    )

    assert response.status_code == 200
    data = response.json()
    returned_ids = {item["id"] for item in data["items"]}
    assert returned_ids == {str(apple.id), str(samsung.id)}
    assert str(other.id) not in returned_ids


@pytest.mark.asyncio
async def test_catalog_multiple_characteristic_filters_are_anded(
    seller_id: UUID,
) -> None:
    match = _make_catalog_product(seller_id)
    match.characteristics.clear()
    match.characteristics.append(CharacteristicEntity(name="brand", value="apple"))
    match.characteristics.append(CharacteristicEntity(name="memory", value="256"))

    no_memory = _make_catalog_product(seller_id)
    no_memory.characteristics.clear()
    no_memory.characteristics.append(CharacteristicEntity(name="brand", value="apple"))

    response = await _get_catalog(
        [match, no_memory],
        params={"filters[brand]": "apple", "filters[memory]": "256"},
    )

    assert response.status_code == 200
    data = response.json()
    assert [item["id"] for item in data["items"]] == [str(match.id)]
