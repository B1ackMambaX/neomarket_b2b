from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies.auth import get_current_seller_id
from app.core.dependencies import get_invoice_service
from app.domain.entities.invoice import InvoiceEntity
from app.schemas.invoice import InvoiceCreate, InvoiceItemResponse, InvoiceResponse
from app.services.invoice_service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _invoice_response(invoice: InvoiceEntity) -> InvoiceResponse:
    return InvoiceResponse(
        id=invoice.id,
        seller_id=invoice.seller_id,
        status=invoice.status,
        items=[
            InvoiceItemResponse(
                id=item.id,
                sku_id=item.sku_id,
                quantity=item.quantity,
                accepted_quantity=item.accepted_quantity,
            )
            for item in invoice.items
        ],
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        accepted_at=invoice.accepted_at,
        accepted_by=invoice.accepted_by,
    )


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать накладную (в статусе CREATED)",
    operation_id="createInvoice",
)
async def create_invoice(
    payload: InvoiceCreate,
    seller_id: Annotated[UUID, Depends(get_current_seller_id)],
    service: Annotated[InvoiceService, Depends(get_invoice_service)],
) -> InvoiceResponse:
    invoice = await service.create_invoice(seller_id=seller_id, payload=payload)
    return _invoice_response(invoice)
