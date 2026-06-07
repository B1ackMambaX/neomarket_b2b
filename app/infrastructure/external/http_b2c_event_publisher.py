import logging
from datetime import datetime, timezone
from typing import override
from uuid import UUID, uuid4

import httpx

from app.domain.events import AbstractEventPublisher

logger = logging.getLogger(__name__)


class HttpB2cEventPublisher(AbstractEventPublisher):
    def __init__(self, url: str, service_key: str) -> None:
        self._url: str = url
        self._service_key: str = service_key

    @override
    async def publish_sku_out_of_stock(self, sku_id: UUID) -> None:
        body = {
            "event_type": "SKU_OUT_OF_STOCK",
            "idempotency_key": str(uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"sku_id": str(sku_id)},
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self._url}/api/v1/b2b/events",
                    json=body,
                    headers={"X-Service-Key": self._service_key},
                )
                _ = response.raise_for_status()
        except Exception:
            logger.exception(
                "Failed to publish SKU_OUT_OF_STOCK to B2C for SKU %s", sku_id
            )

    @override
    async def publish_product_blocked(
        self, product_id: UUID, sku_ids: list[UUID], *, hard_block: bool = False
    ) -> None:
        event_type = "PRODUCT_HARD_BLOCKED" if hard_block else "PRODUCT_BLOCKED"
        body = {
            "event_type": event_type,
            "idempotency_key": str(uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {"product_id": str(product_id)},
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self._url}/api/v1/b2b/events",
                    json=body,
                    headers={"X-Service-Key": self._service_key},
                )
                _ = response.raise_for_status()
        except Exception:
            logger.exception(
                "Failed to publish %s to B2C for product %s", event_type, product_id
            )

    @override
    async def publish_product_deleted(
        self, product_id: UUID, sku_ids: list[UUID]
    ) -> None:
        body = {
            "event_type": "PRODUCT_DELETED",
            "idempotency_key": str(uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "product_id": str(product_id),
                "sku_ids": [str(sku_id) for sku_id in sku_ids],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self._url}/api/v1/b2b/events",
                    json=body,
                    headers={"X-Service-Key": self._service_key},
                )
                _ = response.raise_for_status()
        except Exception:
            logger.exception(
                "Failed to publish PRODUCT_DELETED to B2C for product %s", product_id
            )
