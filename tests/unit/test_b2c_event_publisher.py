import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import pytest

from app.infrastructure.external.http_b2c_event_publisher import HttpB2cEventPublisher


@pytest.mark.asyncio
async def test_publish_product_deleted_includes_sku_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202)

    transport = httpx.MockTransport(handler)

    class _B2cTestClient(httpx.AsyncClient):
        def __init__(self, timeout: float) -> None:
            super().__init__(transport=transport, timeout=timeout)

    monkeypatch.setattr(
        "app.infrastructure.external.http_b2c_event_publisher.httpx.AsyncClient",
        _B2cTestClient,
    )
    publisher = HttpB2cEventPublisher(
        url="http://b2c",
        service_key="service-key",
    )
    product_id = uuid4()
    sku_ids = [uuid4(), uuid4()]

    await publisher.publish_product_deleted(product_id, sku_ids)

    assert len(requests) == 1
    request = requests[0]
    body = cast(dict[str, Any], json.loads(request.content))
    assert request.url.path == "/api/v1/b2b/events"
    assert request.headers["X-Service-Key"] == "service-key"
    assert body["event_type"] == "PRODUCT_DELETED"
    _ = UUID(body["idempotency_key"])
    _ = datetime.fromisoformat(body["occurred_at"])
    assert body["payload"] == {
        "product_id": str(product_id),
        "sku_ids": [str(sku_id) for sku_id in sku_ids],
    }
