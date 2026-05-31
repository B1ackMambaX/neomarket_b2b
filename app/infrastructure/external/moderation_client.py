import logging
from abc import ABC, abstractmethod
from typing import override
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.domain.entities.product import ProductEntity
from app.domain.utils.datetime import utc_now

logger = logging.getLogger(__name__)


class AbstractModerationClient(ABC):
    @abstractmethod
    async def send_product_created(self, product: ProductEntity) -> None: ...


class HttpModerationClient(AbstractModerationClient):
    def __init__(
        self,
        url: str,
        service_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url: str = url
        self._service_key: str = service_key
        self._owns_http_client: bool = http_client is None
        self._http_client: httpx.AsyncClient = http_client or httpx.AsyncClient(
            timeout=5.0
        )

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    @override
    async def send_product_created(self, product: ProductEntity) -> None:
        try:
            payload = {
                "event_type": "PRODUCT_CREATED",
                "idempotency_key": str(
                    uuid5(NAMESPACE_URL, f"{product.id}:PRODUCT_CREATED")
                ),
                "occurred_at": utc_now().isoformat() + "Z",
                "payload": {
                    "product_id": str(product.id),
                    "seller_id": str(product.seller_id),
                    "category_id": str(product.category_id),
                    "queue_priority": 3,
                    "json_after": {
                        "title": product.title,
                        "status": product.status.value,
                    },
                },
            }
            response = await self._http_client.post(
                f"{self._url}/api/v1/b2b/events",
                json=payload,
                headers={"X-Service-Key": self._service_key},
            )
            _ = response.raise_for_status()
        except Exception:
            logger.exception(
                "Failed to send CREATED event to Moderation for product %s", product.id
            )
