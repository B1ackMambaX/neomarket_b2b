from uuid import UUID

from pydantic import BaseModel


class CharacteristicInput(BaseModel):
    name: str
    value: str


class CharacteristicResponse(BaseModel):
    name: str
    value: str
    id: UUID
