from datetime import datetime
from uuid import UUID
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.value_objects.product_status import ProductStatus


class ProductCreate(BaseModel):
    category_id: UUID
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None


class ProductImageUpdate(BaseModel):
    url: str
    ordering: int = 0


class ProductUpdate(BaseModel):
    category_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    images: list[ProductImageUpdate] | None = None


class ProductImageResponse(BaseModel):
    id: UUID
    url: str
    ordering: int


class SkuCreate(BaseModel):
    product_id: UUID
    name: str
    price: int
    active_quantity: int = 0
    is_active: bool = True


class SkuUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = None
    active_quantity: Optional[int] = None
    is_active: Optional[bool] = None


class SkuResponse(BaseModel):
    id: UUID
    name: str
    price: int
    active_quantity: int
    is_active: bool


class ProductResponse(BaseModel):
    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    description: str | None
    status: ProductStatus
    created_at: datetime
    updated_at: datetime
    images: list[ProductImageResponse] = []
    skus: list[SkuResponse] = []
