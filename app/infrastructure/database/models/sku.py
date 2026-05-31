# pyright: reportImportCycles=false
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.models.base import Base

if TYPE_CHECKING:
    from app.infrastructure.database.models.invoice import InvoiceItemModel
    from app.infrastructure.database.models.product import ProductModel


class SkuModel(Base):
    __tablename__: str = "skus"
    __table_args__: tuple[Index, ...] = (
        Index("idx_skus_product_id_is_active", "product_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    discount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    active_quantity: Mapped[int] = mapped_column(Integer, default=0)
    article: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["ProductModel"] = relationship(back_populates="skus")
    invoice_items: Mapped[list["InvoiceItemModel"]] = relationship(back_populates="sku")
    images: Mapped[list["SkuImageModel"]] = relationship(
        back_populates="sku",
        cascade="all, delete-orphan",
        order_by="SkuImageModel.ordering",
    )


class SkuImageModel(Base):
    __tablename__: str = "sku_images"
    __table_args__: tuple[Index, ...] = (
        Index("idx_sku_images_sku_id_ordering", "sku_id", "ordering"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sku_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skus.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sku: Mapped["SkuModel"] = relationship(back_populates="images")
