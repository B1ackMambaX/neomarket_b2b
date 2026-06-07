from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


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


@dataclass
class UnreserveResult:
    order_id: UUID
    processed_at: datetime
    from_cache: bool = False


@dataclass
class FulfillResult:
    order_id: UUID
    processed_at: datetime
    from_cache: bool = False
