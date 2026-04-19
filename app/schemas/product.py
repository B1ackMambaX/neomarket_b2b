from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.value_objects.product_status import ProductStatus


class ProductCreate(BaseModel):
    category_id: UUID
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None


class ProductResponse(BaseModel):
    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    description: str | None
    status: ProductStatus
    created_at: datetime
    updated_at: datetime
