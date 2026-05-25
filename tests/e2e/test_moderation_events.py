from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.security import create_access_token
from app.domain.entities.category import CategoryEntity
from app.domain.entities.product import FieldReportEntity, ProductEntity
from app.domain.events import AbstractEventPublisher
from app.domain.exceptions import NotFoundException
from app.domain.repositories.category_repo import AbstractCategoryRepository
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.seller_repo import AbstractSellerRepository
from app.domain.value_objects.product_status import ProductStatus
from app.schemas.product import ModerationEventRequest
from app.services.product_service import ProductService


class _ModerationProductRepo(AbstractProductRepository):
    def __init__(self, product: ProductEntity):
        self.product = product
        self.processed_keys: set[UUID] = set()
        self.save_count = 0

    async def get_by_id(self, product_id: UUID) -> ProductEntity | None:
        return self.product if self.product.id == product_id else None

    async def get_or_raise(self, product_id: UUID) -> ProductEntity:
        product = await self.get_by_id(product_id)
        if product is None:
            raise NotFoundException("Product not found")
        return product

    async def get_with_skus_and_reports(self, product_id: UUID) -> ProductEntity | None:
        return await self.get_by_id(product_id)

    async def list_by_seller(self, seller_id, status=None, limit=20, offset=0):
        return []

    async def list_by_status(self, status, limit=20, offset=0):
        return []

    async def list_catalog_visible(
        self,
        ids=None,
        category_id=None,
        seller_id=None,
        search=None,
        min_price=None,
        max_price=None,
        characteristic_filters=None,
        sort="created_desc",
        limit=20,
        offset=0,
    ):
        return [], 0

    async def save(self, product: ProductEntity) -> ProductEntity:
        self.product = product
        self.save_count += 1
        return product

    async def delete(self, product_id: UUID) -> None:
        pass

    async def mark_moderation_event_processed(self, idempotency_key: UUID) -> bool:
        if idempotency_key in self.processed_keys:
            return False
        self.processed_keys.add(idempotency_key)
        return True


class _SellerRepo(AbstractSellerRepository):
    async def get_by_id(self, seller_id):
        return None

    async def get_or_raise(self, seller_id):
        return None

    async def get_by_inn(self, inn):
        return None

    async def list(self, limit=20, offset=0):
        return []

    async def save(self, seller):
        return seller


class _CategoryRepo(AbstractCategoryRepository):
    async def get_by_id(self, category_id):
        return CategoryEntity(id=category_id, name="Category")

    async def get_or_raise(self, category_id):
        return CategoryEntity(id=category_id, name="Category")


class _Publisher(AbstractEventPublisher):
    def __init__(self) -> None:
        self.blocked_events: list[tuple[UUID, list[UUID]]] = []

    async def publish_sku_out_of_stock(self, sku_id: UUID) -> None:
        pass

    async def publish_product_blocked(
        self, product_id: UUID, sku_ids: list[UUID], *, hard_block: bool = False
    ) -> None:
        self.blocked_events.append((product_id, sku_ids))


def _make_product(status: ProductStatus = ProductStatus.ON_MODERATION) -> ProductEntity:
    product = ProductEntity(
        id=uuid4(),
        seller_id=uuid4(),
        category_id=uuid4(),
        title="Moderated Product",
        slug="moderated-product",
        status=status,
        blocked=status in {ProductStatus.BLOCKED, ProductStatus.HARD_BLOCKED},
        blocking_reason_id=uuid4() if status == ProductStatus.BLOCKED else None,
        moderator_comment="old comment" if status == ProductStatus.BLOCKED else None,
    )
    if status == ProductStatus.BLOCKED:
        product.field_reports.append(
            FieldReportEntity(product_id=product.id, field_name="title", comment="old report")
        )
    return product


def _event_payload(product_id: UUID, **overrides):
    payload = {
        "idempotency_key": str(uuid4()),
        "product_id": str(product_id),
        "event_type": "MODERATED",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(overrides)
    return payload


async def _post_event(product: ProductEntity, payload: dict, headers: dict[str, str] | None = None):
    from app.core.dependencies import get_product_service
    from app.main import app

    repo = _ModerationProductRepo(product)
    publisher = _Publisher()
    service = ProductService(
        product_repo=repo,
        seller_repo=_SellerRepo(),
        category_repo=_CategoryRepo(),
        event_publisher=publisher,
    )
    app.dependency_overrides[get_product_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/moderation/events",
            json=payload,
            headers=headers if headers is not None else {"X-Service-Key": settings.B2B_TO_MOD_KEY},
        )
    app.dependency_overrides.pop(get_product_service, None)
    return response, repo, publisher


@pytest.mark.asyncio
async def test_moderated_event_clears_blocking_data():
    product = _make_product(ProductStatus.BLOCKED)
    payload = _event_payload(product.id)

    response, repo, publisher = await _post_event(product, payload)

    assert response.status_code == 204
    assert repo.product.status == ProductStatus.MODERATED
    assert repo.product.blocked is False
    assert repo.product.blocking_reason_id is None
    assert repo.product.moderator_comment is None
    assert repo.product.field_reports == []
    assert publisher.blocked_events == []


@pytest.mark.asyncio
async def test_blocked_soft_saves_field_reports():
    product = _make_product()
    reason_id = uuid4()
    payload = _event_payload(
        product.id,
        event_type="BLOCKED",
        hard_block=False,
        blocking_reason_id=str(reason_id),
        moderator_comment="bad description",
        field_reports=[{"field_name": "description", "sku_id": None, "comment": "copied text"}],
    )

    response, repo, publisher = await _post_event(product, payload)

    assert response.status_code == 204
    assert repo.product.status == ProductStatus.BLOCKED
    assert repo.product.blocked is True
    assert repo.product.blocking_reason_id == reason_id
    assert repo.product.field_reports[0].field_name == "description"
    assert publisher.blocked_events == [(product.id, [])]


@pytest.mark.asyncio
async def test_blocked_hard_sets_terminal_status():
    product = _make_product()
    payload = _event_payload(
        product.id,
        event_type="BLOCKED",
        hard_block=True,
        blocking_reason_id=str(uuid4()),
    )

    response, repo, publisher = await _post_event(product, payload)

    assert response.status_code == 204
    assert repo.product.status == ProductStatus.HARD_BLOCKED
    assert repo.product.blocked is True
    assert publisher.blocked_events == [(product.id, [])]


@pytest.mark.asyncio
async def test_hard_blocked_product_rejects_seller_edits():
    from app.core.dependencies import get_product_service
    from app.main import app

    product = _make_product(ProductStatus.HARD_BLOCKED)
    repo = _ModerationProductRepo(product)
    service = ProductService(
        product_repo=repo,
        seller_repo=_SellerRepo(),
        category_repo=_CategoryRepo(),
        event_publisher=_Publisher(),
    )
    token = create_access_token({"sub": str(product.seller_id)}, settings.SECRET_KEY)
    app.dependency_overrides[get_product_service] = lambda: service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        put_response = await client.put(
            f"/api/v1/products/{product.id}",
            json={"title": "New title"},
            headers={"Authorization": f"Bearer {token}"},
        )
        delete_response = await client.delete(
            f"/api/v1/products/{product.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    app.dependency_overrides.pop(get_product_service, None)

    assert put_response.status_code == 403
    assert delete_response.status_code == 403
    assert repo.save_count == 0


@pytest.mark.asyncio
async def test_duplicate_event_same_idempotency_key_no_side_effects():
    product = _make_product()
    repo = _ModerationProductRepo(product)
    publisher = _Publisher()
    service = ProductService(
        product_repo=repo,
        seller_repo=_SellerRepo(),
        category_repo=_CategoryRepo(),
        event_publisher=publisher,
    )
    payload = _event_payload(
        product.id,
        event_type="BLOCKED",
        hard_block=False,
        blocking_reason_id=str(uuid4()),
    )

    first = ModerationEventRequest.model_validate(payload)
    second = ModerationEventRequest.model_validate(
        {
            **payload,
            "hard_block": True,
            "blocking_reason_id": str(uuid4()),
            "moderator_comment": "must not be applied",
        }
    )

    assert await service.apply_moderation_event(first) is True
    assert await service.apply_moderation_event(second) is False
    assert repo.save_count == 1
    assert repo.product.status == ProductStatus.BLOCKED
    assert repo.product.moderator_comment is None
    assert len(publisher.blocked_events) == 1


@pytest.mark.asyncio
async def test_missing_service_key_returns_401():
    product = _make_product()
    payload = _event_payload(product.id)

    response, repo, publisher = await _post_event(product, payload, headers={})

    assert response.status_code == 401
    assert repo.save_count == 0
    assert publisher.blocked_events == []
