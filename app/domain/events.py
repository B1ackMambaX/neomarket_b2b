from abc import ABC, abstractmethod
from uuid import UUID


class AbstractEventPublisher(ABC):

    @abstractmethod
    async def publish_sku_out_of_stock(self, sku_id: UUID) -> None: ...
