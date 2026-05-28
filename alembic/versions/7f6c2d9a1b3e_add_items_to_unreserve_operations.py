"""add_items_to_unreserve_operations

Revision ID: 7f6c2d9a1b3e
Revises: 88f77f5af168
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f6c2d9a1b3e"
down_revision: Union[str, None] = "88f77f5af168"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "unreserve_operations",
        sa.Column("items", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.alter_column("unreserve_operations", "items", server_default=None)


def downgrade() -> None:
    op.drop_column("unreserve_operations", "items")
