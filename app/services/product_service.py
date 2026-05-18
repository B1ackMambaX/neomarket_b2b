import re
from uuid import UUID

from app.domain.entities.category import CategoryEntity
from app.domain.entities.product import CharacteristicEntity, ProductEntity, ProductImageEntity
from app.domain.exceptions import NotFoundException, ValidationException
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

    async def get_product(
        self, seller_id: UUID | None, product_id: UUID
    ) -> tuple[ProductEntity, CategoryEntity]:
        product = await self._product_repo.get_with_skus_and_reports(product_id)
        if product is None:
            raise NotFoundException("Product not found")
        if seller_id is not None and product.seller_id != seller_id:
            raise NotFoundException("Product not found")
        category = await self._category_repo.get_by_id(product.category_id)
        if category is None:
            category = CategoryEntity(id=product.category_id, name="")
        return product, category

    async def list_catalog_products(
        self,
        ids: list[UUID] | None = None,
        category_id: UUID | None = None,
        seller_id: UUID | None = None,
        search: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        sort: str = "created_desc",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[tuple[ProductEntity, CategoryEntity]], int]:
        products, total_count = await self._product_repo.list_catalog_visible(
            ids=ids,
            category_id=category_id,
            seller_id=seller_id,
            search=search,
            min_price=min_price,
            max_price=max_price,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        result = []
        for product in products:
            category = await self._category_repo.get_by_id(product.category_id)
            if category is None:
                category = CategoryEntity(id=product.category_id, name="")
            result.append((product, category))
        return result, total_count
