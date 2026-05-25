class DomainException(Exception):
    code: str = "DOMAIN_ERROR"


class NotFoundException(DomainException):
    code = "NOT_FOUND"


class ValidationException(DomainException):
    code = "INVALID_REQUEST"


class PermissionDeniedException(DomainException):
    code = "PERMISSION_DENIED"


class ForbiddenException(DomainException):
    code = "FORBIDDEN"


class InsufficientStockException(DomainException):
    code = "INSUFFICIENT_STOCK"

    def __init__(self, failed_items: list[dict]) -> None:
        self.failed_items = failed_items
        super().__init__("Insufficient stock for one or more SKUs")
