from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies.auth import get_current_seller_id
from app.core.dependencies import get_invoice_service
from app.schemas.invoice import (
    InvoiceAcceptRequest,
    InvoiceCreate,
    InvoiceItemResponse,
    InvoiceResponse,
)
from app.services.invoice_service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _to_response(invoice) -> InvoiceResponse:
    return InvoiceResponse(
        id=invoice.id,
        seller_id=invoice.seller_id,
        invoice_number=invoice.invoice_number,
        status=invoice.status,
        created_at=invoice.created_at,
        accepted_at=invoice.accepted_at,
        items=[
            InvoiceItemResponse(
                sku_id=item.sku_id,
                quantity=item.quantity,
                price_per_unit=item.price_per_unit,
                total=item.total,
            )
            for item in invoice.items
        ],
        total_amount=invoice.total_amount,
    )


@router.post(
    "/",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать счёт",
    description="Создаёт новый счёт в статусе DRAFT с элементами invoice items.",
)
async def create_invoice(
    payload: InvoiceCreate,
    seller_id: UUID = Depends(get_current_seller_id),
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceResponse:
    invoice = await service.create_invoice(seller_id=seller_id, payload=payload)
    return _to_response(invoice)


@router.post(
    "/accept",
    response_model=InvoiceResponse,
    status_code=status.HTTP_200_OK,
    summary="Принять счёт",
    description="Переводит счёт в статус ACCEPTED и списывает количество по SKU из invoice items.",
)
async def accept_invoice(
    payload: InvoiceAcceptRequest,
    seller_id: UUID = Depends(get_current_seller_id),
    service: InvoiceService = Depends(get_invoice_service),
) -> InvoiceResponse:
    invoice = await service.accept_invoice(seller_id=seller_id, invoice_id=payload.invoice_id)
    return _to_response(invoice)
