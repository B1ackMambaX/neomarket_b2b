from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionFactory
from app.infrastructure.database.repositories.category_repo import (
    SQLAlchemyCategoryRepository,
)
from app.infrastructure.database.repositories.inventory_repo import (
    SQLAlchemyInventoryRepository,
)
from app.infrastructure.database.repositories.product_repo import (
    SQLAlchemyProductRepository,
)
from app.infrastructure.database.repositories.seller_repo import (
    SQLAlchemySellerRepository,
)
from app.infrastructure.database.repositories.sku_repo import SQLAlchemySkuRepository
from app.infrastructure.external.http_b2c_event_publisher import HttpB2cEventPublisher
from app.infrastructure.external.moderation_client import HttpModerationClient
from app.services.inventory_service import InventoryService
from app.services.product_service import ProductService
from app.services.sku_service import SkuService

_moderation_client: HttpModerationClient | None = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_product_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ProductService:
    return ProductService(
        product_repo=SQLAlchemyProductRepository(db),
        seller_repo=SQLAlchemySellerRepository(db),
        category_repo=SQLAlchemyCategoryRepository(db),
        event_publisher=HttpB2cEventPublisher(
            url=settings.B2C_URL,
            service_key=settings.B2B_TO_B2C_KEY,
        ),
        moderation_client=get_moderation_client(),
    )


def get_inventory_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryService:
    return InventoryService(
        inventory_repo=SQLAlchemyInventoryRepository(db),
        event_publisher=HttpB2cEventPublisher(
            url=settings.B2C_URL,
            service_key=settings.B2B_TO_B2C_KEY,
        ),
    )


def get_moderation_client() -> HttpModerationClient:
    global _moderation_client
    if _moderation_client is None:
        _moderation_client = HttpModerationClient(
            url=settings.MODERATION_URL,
            service_key=settings.B2B_TO_MOD_KEY,
        )
    return _moderation_client


async def close_moderation_client() -> None:
    global _moderation_client
    if _moderation_client is not None:
        await _moderation_client.close()
        _moderation_client = None


def get_sku_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    moderation_client: Annotated[HttpModerationClient, Depends(get_moderation_client)],
) -> SkuService:
    return SkuService(
        sku_repo=SQLAlchemySkuRepository(db),
        product_repo=SQLAlchemyProductRepository(db),
        moderation_client=moderation_client,
    )
