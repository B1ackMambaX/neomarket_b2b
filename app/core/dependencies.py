from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionFactory
from app.infrastructure.database.repositories.category_repo import SQLAlchemyCategoryRepository
from app.infrastructure.database.repositories.product_repo import SQLAlchemyProductRepository
from app.infrastructure.database.repositories.seller_repo import SQLAlchemySellerRepository
from app.infrastructure.database.repositories.sku_repo import SQLAlchemySkuRepository
from app.infrastructure.external.moderation_client import HttpModerationClient
from app.services.product_service import ProductService
from app.services.sku_service import SkuService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session


def get_product_service(db: AsyncSession = Depends(get_db)) -> ProductService:
    return ProductService(
        product_repo=SQLAlchemyProductRepository(db),
        seller_repo=SQLAlchemySellerRepository(db),
        category_repo=SQLAlchemyCategoryRepository(db),
    )


def get_moderation_client() -> HttpModerationClient:
    return HttpModerationClient(
        url=settings.MODERATION_URL,
        service_key=settings.B2B_TO_MOD_KEY,
    )


def get_sku_service(
    db: AsyncSession = Depends(get_db),
    moderation_client: HttpModerationClient = Depends(get_moderation_client),
) -> SkuService:
    return SkuService(
        sku_repo=SQLAlchemySkuRepository(db),
        product_repo=SQLAlchemyProductRepository(db),
        moderation_client=moderation_client,
    )
