from typing import ClassVar, Literal, TypedDict
from uuid import UUID


class FailedStockItem(TypedDict):
    sku_id: UUID
    requested: int
    available: int
    reason: Literal["OUT_OF_STOCK", "INSUFFICIENT_STOCK"]


class FailedReservedItem(TypedDict):
    sku_id: UUID
    requested: int
    reserved: int
    reason: Literal["INSUFFICIENT_RESERVED"]


class DomainException(Exception):
    code: ClassVar[str] = "DOMAIN_ERROR"


class NotFoundException(DomainException):
    code: ClassVar[str] = "NOT_FOUND"


class ValidationException(DomainException):
    code: ClassVar[str] = "INVALID_REQUEST"


class PermissionDeniedException(DomainException):
    code: ClassVar[str] = "PERMISSION_DENIED"


class NotOwnerException(DomainException):
    code: ClassVar[str] = "NOT_OWNER"


class ForbiddenException(DomainException):
    code: ClassVar[str] = "FORBIDDEN"


class InsufficientStockException(DomainException):
    code: ClassVar[str] = "INSUFFICIENT_STOCK"
    failed_items: list[FailedStockItem]

    def __init__(self, failed_items: list[FailedStockItem]) -> None:
        self.failed_items = failed_items
        super().__init__("Insufficient stock for one or more SKUs")


class InsufficientReservedException(DomainException):
    code: ClassVar[str] = "INSUFFICIENT_RESERVED"
    failed_items: list[FailedReservedItem]

    def __init__(self, failed_items: list[FailedReservedItem]) -> None:
        self.failed_items = failed_items
        super().__init__("Insufficient reserved quantity for one or more SKUs")


class IdempotencyConflictException(DomainException):
    code: ClassVar[str] = "IDEMPOTENCY_CONFLICT"

    def __init__(self) -> None:
        super().__init__(
            "Request payload conflicts with a previously processed operation"
        )
