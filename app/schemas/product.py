from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.value_objects.product_status import ProductStatus


class ProductImageCreate(BaseModel):
    url: str
    ordering: int = 0


class ProductImageResponse(BaseModel):
    id: UUID
    url: str
    ordering: int


class CharacteristicInput(BaseModel):
    name: str
    value: str


class CharacteristicResponse(BaseModel):
    id: UUID
    name: str
    value: str


class ProductCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    category_id: UUID
    slug: str | None = None
    images: list[ProductImageCreate] = Field(default_factory=list)
    characteristics: list[CharacteristicInput] = Field(default_factory=list)


class ProductResponse(BaseModel):
    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    slug: str
    description: str
    status: ProductStatus
    deleted: bool
    blocking_reason_id: UUID | None
    moderator_comment: str | None
    images: list[ProductImageResponse]
    characteristics: list[CharacteristicResponse]
    skus: list
    created_at: datetime
    updated_at: datetime
