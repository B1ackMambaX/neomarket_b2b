from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities.invoice import InvoiceEntity, InvoiceItemEntity
from app.domain.exceptions import NotFoundException
from app.domain.repositories.invoice_repo import AbstractInvoiceRepository
from app.domain.value_objects.invoice_status import InvoiceStatus
from app.infrastructure.database.models.invoice import InvoiceItemModel, InvoiceModel


class SQLAlchemyInvoiceRepository(AbstractInvoiceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, invoice_id: UUID) -> InvoiceEntity | None:
        result = await self._session.execute(
            select(InvoiceModel)
            .options(selectinload(InvoiceModel.items))
            .where(InvoiceModel.id == invoice_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_or_raise(self, invoice_id: UUID) -> InvoiceEntity:
        entity = await self.get_by_id(invoice_id)
        if entity is None:
            raise NotFoundException(f"Invoice {invoice_id} not found")
        return entity

    async def get_by_number(self, invoice_number: str) -> InvoiceEntity | None:
        result = await self._session.execute(
            select(InvoiceModel)
            .options(selectinload(InvoiceModel.items))
            .where(InvoiceModel.invoice_number == invoice_number)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_seller(
        self,
        seller_id: UUID,
        status: InvoiceStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[InvoiceEntity]:
        query = select(InvoiceModel).where(InvoiceModel.seller_id == seller_id)
        if status is not None:
            query = query.where(InvoiceModel.status == status.value)
        query = query.limit(limit).offset(offset)
        result = await self._session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def save(self, invoice: InvoiceEntity) -> InvoiceEntity:
        model = await self._session.merge(self._to_model(invoice))
        await self._session.flush()
        return self._to_entity(model)

    def _to_entity(self, model: InvoiceModel) -> InvoiceEntity:
        items = [
            InvoiceItemEntity(
                id=item.id,
                invoice_id=item.invoice_id,
                sku_id=item.sku_id,
                quantity=item.quantity,
                price_per_unit=item.price_per_unit,
                created_at=item.created_at,
            )
            for item in getattr(model, "items", [])
        ]
        return InvoiceEntity(
            id=model.id,
            seller_id=model.seller_id,
            invoice_number=model.invoice_number,
            status=InvoiceStatus(model.status),
            created_at=model.created_at,
            accepted_at=model.accepted_at,
            items=items,
        )

    def _to_model(self, entity: InvoiceEntity) -> InvoiceModel:
        model = InvoiceModel(
            id=entity.id,
            seller_id=entity.seller_id,
            invoice_number=entity.invoice_number,
            status=entity.status.value,
            accepted_at=entity.accepted_at,
        )
        model.items = [
            InvoiceItemModel(
                id=item.id,
                invoice_id=item.invoice_id,
                sku_id=item.sku_id,
                quantity=item.quantity,
                price_per_unit=item.price_per_unit,
            )
            for item in entity.items
        ]
        return model
