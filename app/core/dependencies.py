from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionFactory
from app.infrastructure.database.repositories.category_repo import SQLAlchemyCategoryRepository
from app.infrastructure.database.repositories.product_repo import SQLAlchemyProductRepository
from app.infrastructure.database.repositories.seller_repo import SQLAlchemySellerRepository
from app.services.product_service import ProductService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session


def get_product_service(db: AsyncSession = Depends(get_db)) -> ProductService:
    return ProductService(
        product_repo=SQLAlchemyProductRepository(db),
        seller_repo=SQLAlchemySellerRepository(db),
        category_repo=SQLAlchemyCategoryRepository(db),
    )
