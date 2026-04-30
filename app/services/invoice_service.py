from uuid import UUID

from app.domain.entities.invoice import InvoiceEntity, InvoiceItemEntity
from app.domain.exceptions import DomainException, PermissionDeniedException
from app.domain.repositories.invoice_repo import AbstractInvoiceRepository
from app.domain.repositories.sku_repo import AbstractSkuRepository
from app.schemas.invoice import InvoiceCreate


class InvoiceService:
    def __init__(
        self,
        invoice_repo: AbstractInvoiceRepository,
        sku_repo: AbstractSkuRepository,
    ) -> None:
        self._invoice_repo = invoice_repo
        self._sku_repo = sku_repo

    async def create_invoice(self, seller_id: UUID, payload: InvoiceCreate) -> InvoiceEntity:
        if await self._invoice_repo.get_by_number(payload.invoice_number):
            raise DomainException(f"Invoice number {payload.invoice_number} already exists")

        invoice = InvoiceEntity.create(seller_id=seller_id, invoice_number=payload.invoice_number)
        invoice.items = [
            InvoiceItemEntity(
                invoice_id=invoice.id,
                sku_id=item.sku_id,
                quantity=item.quantity,
                price_per_unit=item.price_per_unit,
            )
            for item in payload.items
        ]

        for item in invoice.items:
            await self._sku_repo.get_or_raise(item.sku_id)

        return await self._invoice_repo.save(invoice)

    async def accept_invoice(self, seller_id: UUID, invoice_id: UUID) -> InvoiceEntity:
        invoice = await self._invoice_repo.get_or_raise(invoice_id)
        if invoice.seller_id != seller_id:
            raise PermissionDeniedException("Invoice belongs to another seller")

        invoice.accept()

        for item in invoice.items:
            sku = await self._sku_repo.get_or_raise(item.sku_id)
            sku.decrease_quantity(item.quantity)
            await self._sku_repo.save(sku)

        return await self._invoice_repo.save(invoice)
