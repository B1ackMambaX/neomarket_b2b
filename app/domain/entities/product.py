from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.entities.sku import SkuEntity
from app.domain.exceptions import InvalidProductStateException
from app.domain.utils.datetime import utc_now
from app.domain.value_objects.product_status import ProductStatus


@dataclass
class ProductImageEntity:
    product_id: UUID
    url: str
    id: UUID = field(default_factory=uuid4)
    ordering: int = 0
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class CharacteristicEntity:
    name: str
    value: str
    id: UUID = field(default_factory=uuid4)


@dataclass
class FieldReportEntity:
    product_id: UUID
    field_name: str
    comment: str
    id: UUID = field(default_factory=uuid4)
    sku_id: UUID | None = None


@dataclass
class ProductEntity:
    seller_id: UUID
    category_id: UUID
    title: str
    id: UUID = field(default_factory=uuid4)
    description: str | None = None
    slug: str | None = None
    status: ProductStatus = ProductStatus.CREATED
    deleted: bool = False
    blocked: bool = False
    blocking_reason_id: UUID | None = None
    blocking_reason_title: str | None = None
    moderator_comment: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    moderated_at: datetime | None = None
    images: list[ProductImageEntity] = field(default_factory=list)
    characteristics: list[CharacteristicEntity] = field(default_factory=list)
    skus: list[SkuEntity] = field(default_factory=list)
    field_reports: list[FieldReportEntity] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        seller_id: UUID,
        category_id: UUID,
        title: str,
        description: str | None = None,
        slug: str | None = None,
        images: list[ProductImageEntity] | None = None,
        characteristics: list[CharacteristicEntity] | None = None,
    ) -> "ProductEntity":
        return cls(
            seller_id=seller_id,
            category_id=category_id,
            title=title,
            description=description,
            slug=slug,
            images=images or [],
            characteristics=characteristics or [],
        )

    def submit_for_moderation(self) -> None:
        if self.status != ProductStatus.CREATED:
            raise InvalidProductStateException(
                f"Cannot submit product in status {self.status.value} for moderation"
            )
        self.status = ProductStatus.ON_MODERATION
        self.updated_at = utc_now()

    def approve(self) -> None:
        if self.status != ProductStatus.ON_MODERATION:
            raise InvalidProductStateException(
                f"Cannot approve product in status {self.status.value}"
            )
        self.status = ProductStatus.MODERATED
        self.moderated_at = utc_now()
        self.updated_at = utc_now()

    def block(self, hard: bool = False) -> None:
        self.status = ProductStatus.HARD_BLOCKED if hard else ProductStatus.BLOCKED
        self.blocked = True
        self.updated_at = utc_now()
