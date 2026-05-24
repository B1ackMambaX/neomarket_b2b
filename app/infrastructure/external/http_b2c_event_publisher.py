import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx

from app.domain.events import AbstractEventPublisher

logger = logging.getLogger(__name__)


class HttpB2cEventPublisher(AbstractEventPublisher):
    def __init__(self, url: str, service_key: str) -> None:
        self._url = url
        self._service_key = service_key

    async def publish_sku_out_of_stock(self, sku_id: UUID) -> None:
        pass

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
                response.raise_for_status()
        except Exception:
            logger.exception(
                "Failed to publish %s to B2C for product %s", event_type, product_id
            )
