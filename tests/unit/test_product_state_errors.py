import json
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.api.middleware.error_handler import domain_exception_handler
from app.domain.entities.product import ProductEntity
from app.domain.exceptions import InvalidProductStateException
from app.domain.value_objects.product_status import ProductStatus


def _make_product(status: ProductStatus) -> ProductEntity:
    return ProductEntity(
        id=uuid4(),
        seller_id=uuid4(),
        category_id=uuid4(),
        title="Test Product",
        status=status,
    )


@pytest.mark.asyncio
async def test_invalid_product_state_maps_to_409_contract_error() -> None:
    product = _make_product(ProductStatus.ON_MODERATION)

    with pytest.raises(InvalidProductStateException) as exc_info:
        product.submit_for_moderation()

    response = await domain_exception_handler(
        Request({"type": "http", "method": "GET", "path": "/", "headers": []}),
        exc_info.value,
    )

    assert response.status_code == 409
    assert json.loads(bytes(response.body)) == {
        "code": "INVALID_PRODUCT_STATE",
        "message": "Cannot submit product in status ON_MODERATION for moderation",
    }
