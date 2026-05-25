import asyncio
from uuid import UUID

from app.domain.entities.sku import SkuCharacteristicEntity, SkuEntity
from app.domain.exceptions import ForbiddenException, NotFoundException, PermissionDeniedException, ValidationException
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.sku_repo import AbstractSkuRepository
from app.domain.value_objects.product_status import ProductStatus
from app.infrastructure.external.moderation_client import AbstractModerationClient
from app.schemas.sku import SKUCreate


class SkuService:
    def __init__(
        self,
        sku_repo: AbstractSkuRepository,
        product_repo: AbstractProductRepository,
        moderation_client: AbstractModerationClient,
    ) -> None:
        self._sku_repo = sku_repo
        self._product_repo = product_repo
        self._moderation_client = moderation_client

    async def create_sku(self, seller_id: UUID, payload: SKUCreate) -> SkuEntity:
        product = await self._product_repo.get_by_id(payload.product_id)
        if product is None:
            raise NotFoundException("Product not found")

        if product.seller_id != seller_id:
            raise PermissionDeniedException("Product does not belong to this seller")

        if product.status == ProductStatus.HARD_BLOCKED:
            raise ForbiddenException("Cannot add SKU to hard-blocked product")

        if not payload.images:
            raise ValidationException("image is required")

        image_url = payload.images[0].url

        sku = SkuEntity.create(
            product_id=product.id,
            name=payload.name,
            price=payload.price,
            cost_price=payload.cost_price,
            discount=payload.discount,
            article=payload.article,
            image=image_url,
            characteristics=[
                SkuCharacteristicEntity(name=c.name, value=c.value)
                for c in payload.characteristics
            ],
        )

        existing_count = await self._sku_repo.count_by_product(product.id)
        is_first_sku = existing_count == 0

        saved_sku = await self._sku_repo.save(sku)

        if is_first_sku and product.status == ProductStatus.CREATED:
            product.submit_for_moderation()
            await self._product_repo.save(product)
            # fire-and-forget: event delivery must not block or fail SKU creation
            asyncio.create_task(self._moderation_client.send_product_created(product))

        return saved_sku
