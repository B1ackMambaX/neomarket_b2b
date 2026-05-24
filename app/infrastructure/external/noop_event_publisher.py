from uuid import UUID

from app.domain.events import AbstractEventPublisher


class NoopEventPublisher(AbstractEventPublisher):
    """Production stub — replace with HTTP/outbox implementation when B2C webhook is available."""

    async def publish_sku_out_of_stock(self, sku_id: UUID) -> None:
        pass
