import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.models.base import Base


class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = (
        # Составной: запросы "товары продавца со статусом X"
        Index("idx_products_seller_id_status", "seller_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    seller: Mapped["SellerModel"] = relationship(back_populates="products")  # type: ignore[name-defined]
    images: Mapped[list["ProductImageModel"]] = relationship(back_populates="product", cascade="all, delete-orphan") # type: ignore[name-defined]
    skus: Mapped[list["SkuModel"]] = relationship(back_populates="product", cascade="all, delete-orphan")  # type: ignore[name-defined]
