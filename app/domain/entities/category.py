from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.utils.datetime import utc_now


@dataclass
class CategoryEntity:
    name: str
    id: UUID = field(default_factory=uuid4)
    parent_id: UUID | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)
