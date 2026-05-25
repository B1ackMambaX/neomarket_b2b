from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class ReservationItemResult:
    sku_id: UUID
    quantity: int
    remaining_stock: int


@dataclass
class ReservationResult:
    order_id: UUID
    reserved_at: datetime
    items: list[ReservationItemResult]
    out_of_stock_sku_ids: list[UUID] = field(default_factory=list)
    from_cache: bool = False
