from enum import Enum


class ProductStatus(str, Enum):
    DRAFT = "DRAFT"
    ON_MODERATION = "ON_MODERATION"
    MODERATED = "MODERATED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
