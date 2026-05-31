from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.domain.exceptions import DomainException, ValidationException
from app.domain.utils.datetime import utc_now


@dataclass
class SkuCharacteristicEntity:
    name: str
    value: str
    id: UUID = field(default_factory=uuid4)


@dataclass
class SkuImageEntity:
    url: str
    ordering: int = 0
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class SkuEntity:
    product_id: UUID
    name: str
    price: int  # kopecks
    cost_price: int | None  # kopecks, seller-only
    id: UUID = field(default_factory=uuid4)
    discount: int = 0
    active_quantity: int = 0
    reserved_quantity: int = 0
    article: str | None = None
    images: list[SkuImageEntity] = field(default_factory=list)
    is_active: bool = True
    characteristics: list[SkuCharacteristicEntity] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def image(self) -> str | None:
        if not self.images:
            return None
        return min(self.images, key=lambda image: image.ordering).url

    @classmethod
    def create(
        cls,
        product_id: UUID,
        name: str,
        price: int,
        cost_price: int | None = None,
        discount: int = 0,
        article: str | None = None,
        images: list[SkuImageEntity] | None = None,
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
            images=images or [],
            characteristics=characteristics or [],
        )

    @property
    def price_in_rubles(self) -> Decimal:
        return Decimal(self.price) / 100

    def increase_quantity(self, amount: int) -> None:
        if amount <= 0:
            raise DomainException("Quantity increase must be positive")
        self.active_quantity += amount
        self.updated_at = utc_now()

    def decrease_quantity(self, amount: int) -> None:
        if amount <= 0:
            raise DomainException("Quantity decrease must be positive")
        if self.active_quantity < amount:
            raise DomainException(
                f"Insufficient quantity: {self.active_quantity} < {amount}"
            )
        self.active_quantity -= amount
        self.updated_at = utc_now()

    def deactivate(self) -> None:
        self.is_active = False
        self.updated_at = utc_now()
