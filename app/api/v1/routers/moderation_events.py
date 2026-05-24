from fastapi import APIRouter, Depends, Response, status

from app.api.v1.dependencies.auth import require_moderation_service_key
from app.core.dependencies import get_product_service
from app.schemas.product import ModerationEventRequest
from app.services.product_service import ProductService

router = APIRouter(prefix="/moderation/events", tags=["Moderation Events"])


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Приём событий от Moderation Service",
    operation_id="receiveModerationEvent",
)
async def receive_moderation_event(
    payload: ModerationEventRequest,
    _: None = Depends(require_moderation_service_key),
    service: ProductService = Depends(get_product_service),
) -> Response:
    await service.apply_moderation_event(payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
