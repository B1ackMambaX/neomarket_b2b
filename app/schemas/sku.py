from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import CharacteristicInput, CharacteristicResponse


class SKUImageCreate(BaseModel):
    url: str
    ordering: int = 0


class SKUImageResponse(BaseModel):
    id: UUID
    url: str
    ordering: int


class SKUCreate(BaseModel):
    product_id: UUID
    name: str = Field(min_length=1, max_length=255)
    price: int = Field(ge=0, description="Price in kopecks")
    cost_price: int | None = Field(
        default=None, ge=0, description="Cost price in kopecks (seller-only)"
    )
    discount: int = Field(default=0, ge=0, description="Absolute discount in kopecks")
    article: str | None = None
    images: list[SKUImageCreate] = Field(default_factory=list, min_length=1)
    characteristics: list[CharacteristicInput] = Field(default_factory=list)


class SKUUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    price: int | None = Field(default=None, ge=0, description="Price in kopecks")
    cost_price: int | None = Field(
        default=None, ge=0, description="Cost price in kopecks (seller-only)"
    )
    discount: int | None = Field(
        default=None, ge=0, description="Absolute discount in kopecks"
    )
    article: str | None = None
    characteristics: list[CharacteristicInput] | None = None


class SKUResponse(BaseModel):
    id: UUID
    product_id: UUID
    name: str
    price: int
    discount: int
    cost_price: int | None
    stock_quantity: int
    active_quantity: int
    reserved_quantity: int
    article: str | None
    images: list[SKUImageResponse]
    characteristics: list[CharacteristicResponse]
    created_at: datetime
    updated_at: datetime


class SKUPublicResponse(BaseModel):
    id: UUID
    product_id: UUID
    name: str
    price: int
    discount: int
    stock_quantity: int
    active_quantity: int
    article: str | None
    images: list[SKUImageResponse]
    characteristics: list[CharacteristicResponse]
