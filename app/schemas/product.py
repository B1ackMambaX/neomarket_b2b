from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.value_objects.product_status import ProductStatus
from app.schemas.common import CharacteristicInput, CharacteristicResponse
from app.schemas.sku import SKUPublicResponse, SKUResponse

__all__ = [
    "CharacteristicInput",
    "CharacteristicResponse",
]


class ProductImageCreate(BaseModel):
    url: str
    ordering: int = 0


class ProductImageResponse(BaseModel):
    id: UUID
    url: str
    ordering: int


class ProductCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    category_id: UUID
    slug: str | None = None
    images: list[ProductImageCreate] = Field(default_factory=list)
    characteristics: list[CharacteristicInput] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    category_id: UUID | None = None
    characteristics: list[CharacteristicInput] | None = None


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
    skus: list[SKUResponse]
    created_at: datetime
    updated_at: datetime


# --- GET /products/{id} response schemas ---


class CategoryInProductResponse(BaseModel):
    id: UUID
    name: str


class BlockingReasonInProductResponse(BaseModel):
    id: UUID
    title: str
    comment: str | None


class FieldReportResponse(BaseModel):
    field_name: str
    sku_id: UUID | None
    comment: str


class ProductDetailResponse(BaseModel):
    # All fields from OpenAPI ProductResponse (required)
    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    slug: str | None
    description: str | None
    status: ProductStatus
    deleted: bool
    blocking_reason_id: UUID | None
    moderator_comment: str | None
    images: list[ProductImageResponse]
    characteristics: list[CharacteristicResponse]
    skus: list[SKUResponse]
    created_at: datetime
    updated_at: datetime
    # Extra fields from flow / DoD (superset of OpenAPI)
    blocked: bool
    category: CategoryInProductResponse
    blocking_reason: BlockingReasonInProductResponse | None
    field_reports: list[FieldReportResponse]


class ProductPublicResponse(BaseModel):
    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    slug: str | None
    description: str | None
    status: ProductStatus
    images: list[ProductImageResponse]
    characteristics: list[CharacteristicResponse]
    skus: list[SKUPublicResponse]
    created_at: datetime
    updated_at: datetime


class ProductPublicShortResponse(BaseModel):
    id: UUID
    title: str
    slug: str | None
    status: ProductStatus
    category_id: UUID
    min_price: int | None
    cover_image: str | None
    created_at: datetime


class ProductShortResponse(BaseModel):
    id: UUID
    title: str
    slug: str | None
    status: ProductStatus
    category_id: UUID
    deleted: bool
    created_at: datetime
    min_price: int | None
    cover_image: str | None
    skus_count: int
    total_active_quantity: int


class ProductPaginatedResponse(BaseModel):
    items: list[ProductShortResponse]
    total_count: int
    limit: int
    offset: int


class ProductPublicPaginatedResponse(BaseModel):
    items: list[ProductPublicShortResponse]
    total_count: int
    limit: int
    offset: int


class ProductPublicBatchRequest(BaseModel):
    product_ids: list[UUID] = Field(min_length=1, max_length=100)


class ModerationFieldReport(BaseModel):
    field_name: str
    sku_id: UUID | None = None
    comment: str


class ModerationEventRequest(BaseModel):
    idempotency_key: UUID
    product_id: UUID
    event_type: Literal["MODERATED", "BLOCKED"]
    moderator_id: UUID | None = None
    moderator_comment: str | None = None
    blocking_reason_id: UUID | None = None
    hard_block: bool = False
    field_reports: list[ModerationFieldReport] | None = None
    occurred_at: datetime
