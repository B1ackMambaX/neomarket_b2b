from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.exceptions import DomainException
from app.domain.value_objects.invoice_status import InvoiceStatus


@dataclass
class InvoiceItemEntity:
    invoice_id: UUID
    sku_id: UUID
    quantity: int
    price_per_unit: int  # в копейках
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total(self) -> int:
        return self.quantity * self.price_per_unit


@dataclass
class InvoiceEntity:
    seller_id: UUID
    invoice_number: str
    id: UUID = field(default_factory=uuid4)
    status: InvoiceStatus = InvoiceStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    accepted_at: datetime | None = None
    items: list[InvoiceItemEntity] = field(default_factory=list)

    @classmethod
    def create(cls, seller_id: UUID, invoice_number: str) -> "InvoiceEntity":
        return cls(seller_id=seller_id, invoice_number=invoice_number)

    @property
    def total_amount(self) -> int:
        return sum(item.total for item in self.items)

    def send(self) -> None:
        if self.status != InvoiceStatus.DRAFT:
            raise DomainException(f"Cannot send invoice in status {self.status}")
        if not self.items:
            raise DomainException("Cannot send invoice with no items")
        self.status = InvoiceStatus.SENT

    def accept(self) -> None:
        if self.status != InvoiceStatus.SENT:
            raise DomainException(f"Cannot accept invoice in status {self.status}")
        self.status = InvoiceStatus.ACCEPTED
        self.accepted_at = datetime.utcnow()

    def reject(self) -> None:
        if self.status != InvoiceStatus.SENT:
            raise DomainException(f"Cannot reject invoice in status {self.status}")
        self.status = InvoiceStatus.REJECTED
