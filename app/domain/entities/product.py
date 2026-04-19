from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.exceptions import DomainException
from app.domain.value_objects.product_status import ProductStatus


@dataclass
class ProductImageEntity:
    product_id: UUID
    url: str
    id: UUID = field(default_factory=uuid4)
    ordering: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProductEntity:
    seller_id: UUID
    category_id: UUID
    title: str
    id: UUID = field(default_factory=uuid4)
    description: str | None = None
    status: ProductStatus = ProductStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    moderated_at: datetime | None = None
    images: list[ProductImageEntity] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        seller_id: UUID,
        category_id: UUID,
        title: str,
        description: str | None = None,
    ) -> "ProductEntity":
        return cls(seller_id=seller_id, category_id=category_id, title=title, description=description)

    def submit_for_moderation(self) -> None:
        if self.status != ProductStatus.DRAFT:
            raise DomainException(f"Cannot submit product in status {self.status} for moderation")
        self.status = ProductStatus.ON_MODERATION
        self.updated_at = datetime.utcnow()

    def approve(self) -> None:
        if self.status != ProductStatus.ON_MODERATION:
            raise DomainException(f"Cannot approve product in status {self.status}")
        self.status = ProductStatus.MODERATED
        self.moderated_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def reject(self) -> None:
        if self.status != ProductStatus.ON_MODERATION:
            raise DomainException(f"Cannot reject product in status {self.status}")
        self.status = ProductStatus.REJECTED
        self.updated_at = datetime.utcnow()

    def block(self) -> None:
        self.status = ProductStatus.BLOCKED
        self.updated_at = datetime.utcnow()
