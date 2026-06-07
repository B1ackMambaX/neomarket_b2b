from uuid import UUID, uuid4

from app.domain.entities.invoice import InvoiceEntity, InvoiceItemEntity
from app.domain.exceptions import NotFoundException, NotOwnerException, ValidationException
from app.domain.repositories.invoice_repo import AbstractInvoiceRepository
from app.domain.repositories.product_repo import AbstractProductRepository
from app.domain.repositories.sku_repo import AbstractSkuRepository
from app.domain.value_objects.product_status import ProductStatus
from app.schemas.invoice import InvoiceCreate


class InvoiceService:
    def __init__(
        self,
        invoice_repo: AbstractInvoiceRepository,
        sku_repo: AbstractSkuRepository,
        product_repo: AbstractProductRepository,
    ) -> None:
        self._invoice_repo: AbstractInvoiceRepository = invoice_repo
        self._sku_repo: AbstractSkuRepository = sku_repo
        self._product_repo: AbstractProductRepository = product_repo

    async def create_invoice(
        self,
        seller_id: UUID,
        payload: InvoiceCreate,
    ) -> InvoiceEntity:
        if not payload.items:
            raise ValidationException("At least one item is required")

        sku_ids = [item.sku_id for item in payload.items]
        if len(sku_ids) != len(set(sku_ids)):
            raise ValidationException("Duplicate SKU IDs in items")

        skus = await self._sku_repo.get_many_by_ids(sku_ids)
        sku_map = {sku.id: sku for sku in skus}
        for sku_id in sku_ids:
            if sku_id not in sku_map:
                raise NotFoundException("SKU not found")

        product_ids = list({sku.product_id for sku in skus})
        products = await self._product_repo.get_many_by_ids(product_ids)
        product_map = {p.id: p for p in products}

        for sku in skus:
            if product_map[sku.product_id].seller_id != seller_id:
                raise NotOwnerException(
                    "One or more SKUs do not belong to the authenticated seller"
                )

        for sku in skus:
            if product_map[sku.product_id].status != ProductStatus.MODERATED:
                raise ValidationException(
                    "Invoice can only be created for MODERATED products"
                )

        invoice = InvoiceEntity.create(
            seller_id=seller_id,
            invoice_number=f"INV-{uuid4().hex.upper()}",
        )
        invoice.items = [
            InvoiceItemEntity(
                invoice_id=invoice.id,
                sku_id=item.sku_id,
                quantity=item.quantity,
                price_per_unit=sku_map[item.sku_id].price,
            )
            for item in payload.items
        ]
        return await self._invoice_repo.save(invoice)
