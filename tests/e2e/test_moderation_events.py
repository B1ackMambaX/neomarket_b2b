from datetime import datetime, timezone
from typing import override
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.core.config import settings
from app.core.security import create_access_token
from app.domain.entities.category import CategoryEntity
from app.domain.entities.product import FieldReportEntity, ProductEntity
from app.domain.entities.seller import SellerEntity
from app.domain.events import AbstractEventPublisher
from app.domain.exceptions import NotFoundException
from app.domain.repositories.category_repo import AbstractCategoryRepository
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.seller_repo import AbstractSellerRepository
from app.domain.value_objects.product_status import ProductStatus
from app.schemas.product import ModerationEventRequest
from app.services.product_service import ProductService

ModerationPayloadValue = str | bool | list[dict[str, str | None]]
ModerationPayload = dict[str, ModerationPayloadValue]


class _ModerationProductRepo(AbstractProductRepository):
    def __init__(self, product: ProductEntity) -> None:
        self.product: ProductEntity = product
        self.processed_keys: set[UUID] = set()
        self.save_count: int = 0

    @override
    async def get_by_id(self, product_id: UUID) -> ProductEntity | None:
        return self.product if self.product.id == product_id else None

    @override
    async def get_many_by_ids(self, product_ids: list[UUID]) -> list[ProductEntity]:
        return [self.product] if self.product.id in product_ids else []

    @override
    async def get_by_id_for_update(self, product_id: UUID) -> ProductEntity | None:
        return await self.get_by_id(product_id)

    @override
    async def get_or_raise(self, product_id: UUID) -> ProductEntity:
        product = await self.get_by_id(product_id)
        if product is None:
            raise NotFoundException("Product not found")
        return product

    @override
    async def get_with_skus_and_reports(
        self, product_id: UUID, *, for_update: bool = False
    ) -> ProductEntity | None:
        return await self.get_by_id(product_id)

    @override
    async def list_by_seller(
        self,
        seller_id: UUID,
        status: ProductStatus | None = None,
        include_deleted: bool = False,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ProductEntity], int]:
        return [], 0

    @override
    async def list_by_status(
        self,
        status: ProductStatus,
        limit: int = 20,
        offset: int = 0,
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
        self.product = product
        self.save_count += 1
        return product

    @override
    async def delete(self, product_id: UUID) -> None:
        pass

    @override
    async def mark_moderation_event_processed(self, idempotency_key: UUID) -> bool:
        if idempotency_key in self.processed_keys:
            return False
        self.processed_keys.add(idempotency_key)
        return True


class _SellerRepo(AbstractSellerRepository):
    @override
    async def get_by_id(self, seller_id: UUID) -> SellerEntity | None:
        return None

    @override
    async def get_or_raise(self, seller_id: UUID) -> SellerEntity:
        raise NotFoundException("Seller not found")

    @override
    async def get_by_inn(self, inn: str) -> SellerEntity | None:
        return None

    @override
    async def list(self, limit: int = 20, offset: int = 0) -> list[SellerEntity]:
        return []

    @override
    async def save(self, seller: SellerEntity) -> SellerEntity:
        return seller


class _CategoryRepo(AbstractCategoryRepository):
    @override
    async def get_by_id(self, category_id: UUID) -> CategoryEntity | None:
        return CategoryEntity(id=category_id, name="Category")

    @override
    async def get_or_raise(self, category_id: UUID) -> CategoryEntity:
        return CategoryEntity(id=category_id, name="Category")


class _Publisher(AbstractEventPublisher):
    def __init__(self) -> None:
        self.blocked_events: list[tuple[UUID, list[UUID]]] = []

    @override
    async def publish_sku_out_of_stock(self, sku_id: UUID) -> None:
        pass

    @override
    async def publish_product_blocked(
        self, product_id: UUID, sku_ids: list[UUID], *, hard_block: bool = False
    ) -> None:
        self.blocked_events.append((product_id, sku_ids))

    @override
    async def publish_product_deleted(
        self, product_id: UUID, sku_ids: list[UUID]
    ) -> None:
        pass


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
            FieldReportEntity(
                product_id=product.id, field_name="title", comment="old report"
            )
        )
    return product


def _event_payload(
    product_id: UUID,
    **overrides: ModerationPayloadValue,
) -> ModerationPayload:
    payload: ModerationPayload = {
        "idempotency_key": str(uuid4()),
        "product_id": str(product_id),
        "event_type": "MODERATED",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(overrides)
    return payload


async def _post_event(
    product: ProductEntity,
    payload: ModerationPayload,
    headers: dict[str, str] | None = None,
) -> tuple[Response, _ModerationProductRepo, _Publisher]:
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
            headers=headers
            if headers is not None
            else {"X-Service-Key": settings.B2B_TO_MOD_KEY},
        )
    _ = app.dependency_overrides.pop(get_product_service, None)
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
        field_reports=[
            {"field_name": "description", "sku_id": None, "comment": "copied text"}
        ],
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
    _ = app.dependency_overrides.pop(get_product_service, None)

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


@pytest.mark.parametrize("headers", [{}, {"X-Service-Key": "invalid"}])
@pytest.mark.asyncio
async def test_invalid_service_key_returns_401_with_error_shape(
    headers: dict[str, str],
):
    product = _make_product()
    payload = _event_payload(product.id)

    response, repo, publisher = await _post_event(product, payload, headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "code": "UNAUTHORIZED",
        "message": "Invalid service key",
    }
    assert repo.save_count == 0
    assert publisher.blocked_events == []
