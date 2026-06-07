from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.value_objects.invoice_status import InvoiceStatus


class InvoiceItemCreate(BaseModel):
    sku_id: UUID
    quantity: int = Field(gt=0)


class InvoiceCreate(BaseModel):
    items: list[InvoiceItemCreate] = Field(json_schema_extra={"minItems": 1})


class InvoiceItemResponse(BaseModel):
    id: UUID
    sku_id: UUID
    quantity: int
    accepted_quantity: int


class InvoiceResponse(BaseModel):
    id: UUID
    seller_id: UUID
    status: InvoiceStatus
    items: list[InvoiceItemResponse]
    created_at: datetime
    updated_at: datetime
    accepted_at: datetime | None = None
    accepted_by: UUID | None = None
