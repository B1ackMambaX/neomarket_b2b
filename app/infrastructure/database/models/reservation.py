import uuid
from datetime import datetime
from typing import TypedDict

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class SerializedInventoryItem(TypedDict):
    sku_id: str
    quantity: int


class SerializedReservationItem(SerializedInventoryItem):
    remaining_stock: int


class SerializedReservationResult(TypedDict):
    order_id: str
    reserved_at: str
    items: list[SerializedReservationItem]


class ReserveOperationModel(Base):
    __tablename__: str = "reserve_operations"

    idempotency_key: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    result: Mapped[SerializedReservationResult] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UnreserveOperationModel(Base):
    __tablename__: str = "unreserve_operations"

    order_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    items: Mapped[list[SerializedInventoryItem]] = mapped_column(JSON, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
