# pyright: reportImportCycles=false
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.models.base import Base

if TYPE_CHECKING:
    from app.infrastructure.database.models.product_characteristic import (
        ProductCharacteristicModel,
    )
    from app.infrastructure.database.models.product_field_report import (
        ProductFieldReportModel,
    )
    from app.infrastructure.database.models.product_image import ProductImageModel
    from app.infrastructure.database.models.seller import SellerModel
    from app.infrastructure.database.models.sku import SkuModel


class ProductModel(Base):
    __tablename__: str = "products"
    __table_args__: tuple[Index, ...] = (
        Index("idx_products_seller_id_status", "seller_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    seller_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sellers.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="CREATED")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocking_reason_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    blocking_reason_title: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    moderator_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    moderated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    seller: Mapped["SellerModel"] = relationship(back_populates="products")
    images: Mapped[list["ProductImageModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    characteristics: Mapped[list["ProductCharacteristicModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    skus: Mapped[list["SkuModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    field_reports: Mapped[list["ProductFieldReportModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
