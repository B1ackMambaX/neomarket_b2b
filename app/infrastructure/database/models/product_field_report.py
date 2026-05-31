# pyright: reportImportCycles=false
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.models.base import Base

if TYPE_CHECKING:
    from app.infrastructure.database.models.product import ProductModel


class ProductFieldReportModel(Base):
    __tablename__: str = "product_field_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    sku_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False)

    product: Mapped["ProductModel"] = relationship(back_populates="field_reports")
