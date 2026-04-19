from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.invoice import InvoiceEntity
from app.domain.value_objects.invoice_status import InvoiceStatus


class AbstractInvoiceRepository(ABC):

    @abstractmethod
    async def get_by_id(self, invoice_id: UUID) -> InvoiceEntity | None: ...

    @abstractmethod
    async def get_or_raise(self, invoice_id: UUID) -> InvoiceEntity: ...

    @abstractmethod
    async def get_by_number(self, invoice_number: str) -> InvoiceEntity | None: ...

    @abstractmethod
    async def list_by_seller(
        self,
        seller_id: UUID,
        status: InvoiceStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[InvoiceEntity]: ...

    @abstractmethod
    async def save(self, invoice: InvoiceEntity) -> InvoiceEntity: ...
