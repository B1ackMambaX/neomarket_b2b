from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.utils.datetime import utc_now
from app.domain.value_objects.invoice_status import InvoiceStatus


@dataclass
class InvoiceItemEntity:
    invoice_id: UUID
    sku_id: UUID
    quantity: int
    price_per_unit: int  # в копейках
    accepted_quantity: int = 0
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)

    @property
    def total(self) -> int:
        return self.quantity * self.price_per_unit


@dataclass
class InvoiceEntity:
    seller_id: UUID
    invoice_number: str
    id: UUID = field(default_factory=uuid4)
    status: InvoiceStatus = InvoiceStatus.CREATED
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    accepted_at: datetime | None = None
    accepted_by: UUID | None = None
    items: list[InvoiceItemEntity] = field(default_factory=list)

    @classmethod
    def create(cls, seller_id: UUID, invoice_number: str) -> "InvoiceEntity":
        return cls(seller_id=seller_id, invoice_number=invoice_number)

    @property
    def total_amount(self) -> int:
        return sum(item.total for item in self.items)
