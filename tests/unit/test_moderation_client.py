import json
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest

from app.domain.entities.product import ProductEntity
from app.domain.value_objects.product_status import ProductStatus
from app.infrastructure.external.moderation_client import HttpModerationClient


@pytest.mark.asyncio
async def test_send_product_edited_matches_moderation_openapi() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = HttpModerationClient(
            url="http://moderation",
            service_key="service-key",
            http_client=http_client,
        )
        product = ProductEntity(
            seller_id=uuid4(),
            category_id=uuid4(),
            title="Product",
            status=ProductStatus.ON_MODERATION,
        )
        before: dict[str, object] = {"status": "MODERATED"}
        after: dict[str, object] = {"status": "ON_MODERATION"}

        await client.send_product_edited(product, before, after)

    assert len(requests) == 1
    request = requests[0]
    body = cast(dict[str, Any], json.loads(request.content))
    payload = cast(dict[str, Any], body["payload"])
    assert request.url.path == "/api/v1/b2b/events"
    assert request.headers["X-Service-Key"] == "service-key"
    assert body["event_type"] == "PRODUCT_EDITED"
    _ = UUID(body["idempotency_key"])
    _ = datetime.fromisoformat(body["occurred_at"].replace("Z", "+00:00"))
    assert payload["product_id"] == str(product.id)
    assert payload["seller_id"] == str(product.seller_id)
    assert payload["json_before"] == before
    assert payload["json_after"] == after


@pytest.mark.asyncio
async def test_send_product_deleted_matches_moderation_openapi() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = HttpModerationClient(
            url="http://moderation",
            service_key="service-key",
            http_client=http_client,
        )
        product = ProductEntity(
            seller_id=uuid4(),
            category_id=uuid4(),
            title="Product",
            deleted=True,
        )

        await client.send_product_deleted(product)

    assert len(requests) == 1
    request = requests[0]
    body = cast(dict[str, Any], json.loads(request.content))
    payload = cast(dict[str, Any], body["payload"])
    assert request.url.path == "/api/v1/b2b/events"
    assert request.headers["X-Service-Key"] == "service-key"
    assert body["event_type"] == "PRODUCT_DELETED"
    _ = UUID(body["idempotency_key"])
    _ = datetime.fromisoformat(body["occurred_at"].replace("Z", "+00:00"))
    assert payload == {"product_id": str(product.id)}


@pytest.mark.asyncio
async def test_send_product_deleted_idempotency_key_tracks_deletion_version() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = HttpModerationClient(
            url="http://moderation",
            service_key="service-key",
            http_client=http_client,
        )
        product = ProductEntity(
            seller_id=uuid4(),
            category_id=uuid4(),
            title="Product",
        )

        await client.send_product_deleted(product)
        await client.send_product_deleted(product)
        product.updated_at += timedelta(microseconds=1)
        await client.send_product_deleted(product)

    keys = [
        cast(dict[str, Any], json.loads(request.content))["idempotency_key"]
        for request in requests
    ]
    assert keys[0] == keys[1]
    assert keys[1] != keys[2]
