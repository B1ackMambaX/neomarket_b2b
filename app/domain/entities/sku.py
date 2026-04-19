from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.exceptions import DomainException


@dataclass
class SkuEntity:
    product_id: UUID
    name: str
    price: int  # в копейках
    id: UUID = field(default_factory=uuid4)
    active_quantity: int = 0
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def create(cls, product_id: UUID, name: str, price: int) -> "SkuEntity":
        if price < 0:
            raise DomainException("SKU price cannot be negative")
        return cls(product_id=product_id, name=name, price=price)

    @property
    def price_in_rubles(self) -> Decimal:
        return Decimal(self.price) / 100

    def increase_quantity(self, amount: int) -> None:
        if amount <= 0:
            raise DomainException("Quantity increase must be positive")
        self.active_quantity += amount
        self.updated_at = datetime.utcnow()

    def decrease_quantity(self, amount: int) -> None:
        if amount <= 0:
            raise DomainException("Quantity decrease must be positive")
        if self.active_quantity < amount:
            raise DomainException(f"Insufficient quantity: {self.active_quantity} < {amount}")
        self.active_quantity -= amount
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        self.is_active = False
        self.updated_at = datetime.utcnow()
