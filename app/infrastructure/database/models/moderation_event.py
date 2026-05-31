import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class ModerationEventModel(Base):
    __tablename__: str = "moderation_events"

    sender_service: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
