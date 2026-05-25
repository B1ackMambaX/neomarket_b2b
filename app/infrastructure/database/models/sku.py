import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.models.base import Base


class SkuModel(Base):
    __tablename__ = "skus"
    __table_args__ = (
        Index("idx_skus_product_id_is_active", "product_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    discount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    active_quantity: Mapped[int] = mapped_column(Integer, default=0)
    article: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    product: Mapped["ProductModel"] = relationship(back_populates="skus")  # type: ignore[name-defined]
    invoice_items: Mapped[list["InvoiceItemModel"]] = relationship(back_populates="sku")  # type: ignore[name-defined]
