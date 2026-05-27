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
from app.infrastructure.external.noop_event_publisher import NoopEventPublisher
from app.services.inventory_service import InventoryService
from app.services.product_service import ProductService
from app.services.sku_service import SkuService


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
    )


def get_inventory_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryService:
    return InventoryService(
        inventory_repo=SQLAlchemyInventoryRepository(db),
        event_publisher=NoopEventPublisher(),
    )


def get_moderation_client() -> HttpModerationClient:
    return HttpModerationClient(
        url=settings.MODERATION_URL,
        service_key=settings.B2B_TO_MOD_KEY,
    )


def get_sku_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    moderation_client: Annotated[HttpModerationClient, Depends(get_moderation_client)],
) -> SkuService:
    return SkuService(
        sku_repo=SQLAlchemySkuRepository(db),
        product_repo=SQLAlchemyProductRepository(db),
        moderation_client=moderation_client,
    )
