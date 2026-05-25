class DomainException(Exception):
    code: str = "DOMAIN_ERROR"


class NotFoundException(DomainException):
    code = "NOT_FOUND"


class ValidationException(DomainException):
    code = "INVALID_REQUEST"


class PermissionDeniedException(DomainException):
    code = "PERMISSION_DENIED"
