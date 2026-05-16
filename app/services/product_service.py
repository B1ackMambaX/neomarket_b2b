import re
from uuid import UUID

from app.domain.entities.product import CharacteristicEntity, ProductEntity, ProductImageEntity
from app.domain.exceptions import ValidationException
from app.domain.repositories.category_repo import AbstractCategoryRepository
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.seller_repo import AbstractSellerRepository
from app.schemas.product import ProductCreate


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


class ProductService:
    def __init__(
        self,
        product_repo: AbstractProductRepository,
        seller_repo: AbstractSellerRepository,
        category_repo: AbstractCategoryRepository,
    ) -> None:
        self._product_repo = product_repo
        self._seller_repo = seller_repo
        self._category_repo = category_repo

    async def create_product(self, seller_id: UUID, payload: ProductCreate) -> ProductEntity:
        await self._seller_repo.get_or_raise(seller_id)

        if not payload.images:
            raise ValidationException("At least one image is required")

        await self._category_repo.get_or_raise(payload.category_id)

        product = ProductEntity.create(
            seller_id=seller_id,
            category_id=payload.category_id,
            title=payload.title,
            description=payload.description,
            slug=payload.slug or _slugify(payload.title),
            characteristics=[
                CharacteristicEntity(name=c.name, value=c.value)
                for c in payload.characteristics
            ],
        )
        for img in payload.images:
            product.images.append(
                ProductImageEntity(product_id=product.id, url=img.url, ordering=img.ordering)
            )

        return await self._product_repo.save(product)
