"""add_categories_and_product_fields

Revision ID: a3c9e1d72b45
Revises: f15118915d7c
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3c9e1d72b45"
down_revision: Union[str, None] = "f15118915d7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_categories_parent_id"), "categories", ["parent_id"], unique=False)

    op.create_table(
        "product_characteristics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_product_characteristics_product_id"), "product_characteristics", ["product_id"], unique=False
    )

    op.add_column("products", sa.Column("slug", sa.String(length=500), nullable=True))
    op.add_column("products", sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("products", sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("products", sa.Column("blocking_reason_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("moderator_comment", sa.Text(), nullable=True))

    # Rename existing DRAFT statuses to CREATED
    op.execute("UPDATE products SET status = 'CREATED' WHERE status = 'DRAFT'")


def downgrade() -> None:
    op.execute("UPDATE products SET status = 'DRAFT' WHERE status = 'CREATED'")

    op.drop_column("products", "moderator_comment")
    op.drop_column("products", "blocking_reason_id")
    op.drop_column("products", "blocked")
    op.drop_column("products", "deleted")
    op.drop_column("products", "slug")

    op.drop_index(op.f("ix_product_characteristics_product_id"), table_name="product_characteristics")
    op.drop_table("product_characteristics")

    op.drop_index(op.f("ix_categories_parent_id"), table_name="categories")
    op.drop_table("categories")
