from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.value_objects.seller_status import SellerStatus


@dataclass
class SellerEntity:
    company_name: str
    id: UUID = field(default_factory=uuid4)
    inn: str | None = None
    status: SellerStatus = SellerStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def create(cls, company_name: str, inn: str | None = None) -> "SellerEntity":
        return cls(company_name=company_name, inn=inn)
