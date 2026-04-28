from uuid import UUID

from app.domain.entities.product import ProductEntity, ProductImageEntity
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.seller_repo import AbstractSellerRepository
from app.schemas.product import ProductCreate, ProductUpdate


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

    async def get_product_by_id(self, product_id: UUID) -> ProductEntity | None:
        return await self._product_repo.get_by_id(product_id)

    async def update_product(
        self,
        product_id: UUID,
        payload: ProductUpdate,
    ) -> ProductEntity:
        product = await self._product_repo.get_or_raise(product_id)

        if payload.category_id is not None:
            product.category_id = payload.category_id

        if payload.title is not None:
            product.title = payload.title

        if payload.description is not None:
            product.description = payload.description

        images = None

        if payload.images is not None:
            images = [
                ProductImageEntity(
                    product_id=product.id,
                    url=image.url,
                    ordering=image.ordering,
                )
                for image in payload.images
            ]

        return await self._product_repo.update(product, images)
