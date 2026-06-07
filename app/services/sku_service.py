import asyncio
import logging
from uuid import UUID

from app.domain.entities.sku import SkuCharacteristicEntity, SkuEntity, SkuImageEntity
from app.domain.exceptions import (
    ForbiddenException,
    NotFoundException,
    NotOwnerException,
)
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.sku_repo import AbstractSkuRepository
from app.domain.value_objects.product_status import ProductStatus
from app.domain.utils.datetime import utc_now
from app.infrastructure.external.moderation_client import (
    AbstractModerationClient,
    moderation_snapshot,
)
from app.schemas.sku import SKUCreate, SKUUpdate

logger = logging.getLogger(__name__)


class SkuService:
    def __init__(
        self,
        sku_repo: AbstractSkuRepository,
        product_repo: AbstractProductRepository,
        moderation_client: AbstractModerationClient,
    ) -> None:
        self._sku_repo: AbstractSkuRepository = sku_repo
        self._product_repo: AbstractProductRepository = product_repo
        self._moderation_client: AbstractModerationClient = moderation_client
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _track_background_task(self, task: asyncio.Task[None]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(self._log_background_task_result)

    @staticmethod
    def _log_background_task_result(task: asyncio.Task[None]) -> None:
        try:
            _ = task.result()
        except asyncio.CancelledError:
            logger.warning("Background moderation delivery task was cancelled")
        except Exception:
            logger.exception("Background moderation delivery task failed")

    async def create_sku(self, seller_id: UUID, payload: SKUCreate) -> SkuEntity:
        product = await self._product_repo.get_by_id_for_update(payload.product_id)
        if product is None:
            raise NotFoundException("Product not found")

        if product.seller_id != seller_id:
            raise NotOwnerException("Product does not belong to this seller")

        if product.status == ProductStatus.HARD_BLOCKED:
            raise ForbiddenException("Cannot add SKU to hard-blocked product")

        sku = SkuEntity.create(
            product_id=product.id,
            name=payload.name,
            price=payload.price,
            cost_price=payload.cost_price,
            discount=payload.discount,
            article=payload.article,
            images=[
                SkuImageEntity(url=image.url, ordering=image.ordering)
                for image in payload.images
            ],
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
            _ = await self._product_repo.save(product)
            self._track_background_task(
                asyncio.create_task(
                    self._moderation_client.send_product_created(product)
                )
            )

        return saved_sku

    async def update_sku(
        self,
        seller_id: UUID,
        sku_id: UUID,
        payload: SKUUpdate,
    ) -> SkuEntity:
        sku = await self._sku_repo.get_by_id_for_update(sku_id)
        if sku is None:
            raise NotFoundException("SKU not found")

        product = await self._product_repo.get_by_id_for_update(sku.product_id)
        if product is None:
            raise NotFoundException("Product not found")
        if product.seller_id != seller_id:
            raise NotOwnerException(
                "Product does not belong to the authenticated seller"
            )
        if product.status == ProductStatus.HARD_BLOCKED:
            raise ForbiddenException("Cannot edit hard-blocked product")

        json_before = moderation_snapshot(product)
        if payload.name is not None:
            sku.name = payload.name
        if payload.price is not None:
            sku.price = payload.price
        if "cost_price" in payload.model_fields_set:
            sku.cost_price = payload.cost_price
        if payload.discount is not None:
            sku.discount = payload.discount
        if "article" in payload.model_fields_set:
            sku.article = payload.article
        if payload.characteristics is not None:
            sku.characteristics = [
                SkuCharacteristicEntity(name=c.name, value=c.value)
                for c in payload.characteristics
            ]
        sku.updated_at = utc_now()

        should_resubmit = product.resubmit_after_edit()

        saved_sku = await self._sku_repo.save(sku)
        if should_resubmit:
            saved_product = await self._product_repo.save(product)
            all_skus_after = [
                saved_sku if s.id == saved_sku.id else s for s in product.skus
            ]
            await self._moderation_client.send_product_edited(
                saved_product,
                json_before=json_before,
                json_after=moderation_snapshot(saved_product, skus=all_skus_after),
            )
        return saved_sku
