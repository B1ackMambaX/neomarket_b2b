import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.models.base import Base


class InvoiceModel(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("idx_invoices_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    seller: Mapped["SellerModel"] = relationship(back_populates="invoices")  # type: ignore[name-defined]
    items: Mapped[list["InvoiceItemModel"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class InvoiceItemModel(Base):
    __tablename__ = "invoice_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    sku_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skus.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_unit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped["InvoiceModel"] = relationship(back_populates="items")
    sku: Mapped["SkuModel"] = relationship(back_populates="invoice_items")  # type: ignore[name-defined]
