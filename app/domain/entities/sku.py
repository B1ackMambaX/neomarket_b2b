from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.exceptions import DomainException, ValidationException


@dataclass
class SkuCharacteristicEntity:
    name: str
    value: str
    id: UUID = field(default_factory=uuid4)


@dataclass
class SkuEntity:
    product_id: UUID
    name: str
    price: int       # kopecks
    cost_price: int | None  # kopecks, seller-only
    id: UUID = field(default_factory=uuid4)
    discount: int = 0
    active_quantity: int = 0
    reserved_quantity: int = 0
    article: str | None = None
    image: str | None = None  # primary image URL
    is_active: bool = True
    characteristics: list[SkuCharacteristicEntity] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def create(
        cls,
        product_id: UUID,
        name: str,
        price: int,
        cost_price: int | None = None,
        discount: int = 0,
        article: str | None = None,
        image: str | None = None,
        characteristics: list[SkuCharacteristicEntity] | None = None,
    ) -> "SkuEntity":
        if price < 0:
            raise ValidationException("price must be >= 0 (kopecks)")
        if cost_price is not None and cost_price < 0:
            raise ValidationException("cost_price must be >= 0 (kopecks)")
        if discount < 0:
            raise ValidationException("discount must be >= 0")
        return cls(
            product_id=product_id,
            name=name,
            price=price,
            cost_price=cost_price,
            discount=discount,
            article=article,
            image=image,
            characteristics=characteristics or [],
        )

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
