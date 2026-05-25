"""add_moderation_events

Revision ID: 2c2a2c7f6c4d
Revises: 88f77f5af168
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c2a2c7f6c4d"
down_revision: Union[str, None] = "88f77f5af168"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "moderation_events",
        sa.Column("sender_service", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("sender_service", "idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("moderation_events")
