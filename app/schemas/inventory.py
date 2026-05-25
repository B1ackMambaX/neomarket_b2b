from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class InventoryItemRequest(BaseModel):
    sku_id: UUID
    quantity: int = Field(ge=1)


class ReserveRequest(BaseModel):
    idempotency_key: UUID
    order_id: UUID
    items: list[InventoryItemRequest] = Field(min_length=1)


class ReserveItemResponse(BaseModel):
    sku_id: UUID
    reserved_quantity: int
    remaining_stock: int


class ReserveSuccessResponse(BaseModel):
    order_id: UUID
    status: str = "RESERVED"
    reserved_at: datetime
    reserved: bool = True
    items: list[ReserveItemResponse]


class FailedItemDetail(BaseModel):
    sku_id: UUID
    requested: int
    available: int
    reason: str


class UnreserveItemRequest(BaseModel):
    sku_id: UUID
    quantity: int = Field(ge=1)


class UnreserveRequest(BaseModel):
    order_id: UUID
    items: list[UnreserveItemRequest] = Field(min_length=1)


class UnreserveResponse(BaseModel):
    order_id: UUID
    status: str = "UNRESERVED"
    processed_at: datetime
