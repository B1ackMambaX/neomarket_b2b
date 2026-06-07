"""add_sku_characteristics

Revision ID: c3b2a1d4e5f6
Revises: 4a9b7c1d2e3f, 7f6c2d9a1b3e
Create Date: 2026-06-07 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3b2a1d4e5f6"
down_revision: Union[str, tuple[str, str], None] = (
    "4a9b7c1d2e3f",
    "7f6c2d9a1b3e",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sku_characteristics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=1000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sku_characteristics_sku_id"),
        "sku_characteristics",
        ["sku_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_sku_characteristics_sku_id"),
        table_name="sku_characteristics",
    )
    op.drop_table("sku_characteristics")
