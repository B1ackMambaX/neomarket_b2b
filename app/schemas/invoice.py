from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, conint

from app.domain.value_objects.invoice_status import InvoiceStatus


class InvoiceItemCreate(BaseModel):
    sku_id: UUID
    quantity: conint(gt=0)
    price_per_unit: conint(gt=0)


class InvoiceCreate(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=100)
    items: list[InvoiceItemCreate] = Field(min_items=1)


class InvoiceAcceptRequest(BaseModel):
    invoice_id: UUID


class InvoiceItemResponse(BaseModel):
    sku_id: UUID
    quantity: int
    price_per_unit: int
    total: int


class InvoiceResponse(BaseModel):
    id: UUID
    seller_id: UUID
    invoice_number: str
    status: InvoiceStatus
    created_at: datetime
    accepted_at: datetime | None
    items: list[InvoiceItemResponse]
    total_amount: int
