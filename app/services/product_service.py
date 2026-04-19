from uuid import UUID

from app.domain.entities.product import ProductEntity
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.seller_repo import AbstractSellerRepository
from app.schemas.product import ProductCreate


class ProductService:
    def __init__(
        self,
        product_repo: AbstractProductRepository,
        seller_repo: AbstractSellerRepository,
    ) -> None:
        self._product_repo = product_repo
        self._seller_repo = seller_repo

    async def create_product(self, seller_id: UUID, payload: ProductCreate) -> ProductEntity:
        await self._seller_repo.get_or_raise(seller_id)

        product = ProductEntity.create(
            seller_id=seller_id,
            category_id=payload.category_id,
            title=payload.title,
            description=payload.description,
        )
        return await self._product_repo.save(product)
