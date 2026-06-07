"""add fulfill operations

Revision ID: b8d3e4f5a6c7
Revises: e7a1b2c3d4e5
Create Date: 2026-06-07 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d3e4f5a6c7"
down_revision: Union[str, None] = "e7a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fulfill_operations",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("order_id"),
    )


def downgrade() -> None:
    op.drop_table("fulfill_operations")
