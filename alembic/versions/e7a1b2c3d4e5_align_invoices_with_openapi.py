"""align invoices with OpenAPI

Revision ID: e7a1b2c3d4e5
Revises: c3b2a1d4e5f6
Create Date: 2026-06-07 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7a1b2c3d4e5"
down_revision: Union[str, None] = "c3b2a1d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column("invoices", sa.Column("accepted_by", sa.Uuid(), nullable=True))
    op.add_column(
        "invoice_items",
        sa.Column(
            "accepted_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE invoices SET status = 'CREATED' WHERE status IN ('DRAFT', 'SENT')"
    )
    op.execute("UPDATE invoices SET status = 'CANCELLED' WHERE status = 'REJECTED'")


def downgrade() -> None:
    op.execute("UPDATE invoices SET status = 'DRAFT' WHERE status = 'CREATED'")
    op.execute("UPDATE invoices SET status = 'REJECTED' WHERE status = 'CANCELLED'")
    op.drop_column("invoice_items", "accepted_quantity")
    op.drop_column("invoices", "accepted_by")
    op.drop_column("invoices", "updated_at")
