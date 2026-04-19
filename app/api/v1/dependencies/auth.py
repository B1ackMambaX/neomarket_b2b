from uuid import UUID

from fastapi import Header, HTTPException, status


async def get_current_seller_id(x_seller_id: UUID = Header(...)) -> UUID:
    # TODO: заменить на декодирование JWT после реализации auth-сервиса
    if not x_seller_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return x_seller_id
