"""add_sku_images

Revision ID: 4a9b7c1d2e3f
Revises: 2c2a2c7f6c4d
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a9b7c1d2e3f"
down_revision: Union[str, None] = "2c2a2c7f6c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sku_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("ordering", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sku_images_sku_id"), "sku_images", ["sku_id"], unique=False)
    op.create_index(
        "idx_sku_images_sku_id_ordering",
        "sku_images",
        ["sku_id", "ordering"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO sku_images (id, sku_id, url, ordering)
        SELECT (
            substr(md5(id::text || ':0'), 1, 8) || '-' ||
            substr(md5(id::text || ':0'), 9, 4) || '-' ||
            substr(md5(id::text || ':0'), 13, 4) || '-' ||
            substr(md5(id::text || ':0'), 17, 4) || '-' ||
            substr(md5(id::text || ':0'), 21, 12)
        )::uuid,
        id,
        image,
        0
        FROM skus
        WHERE image IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("idx_sku_images_sku_id_ordering", table_name="sku_images")
    op.drop_index(op.f("ix_sku_images_sku_id"), table_name="sku_images")
    op.drop_table("sku_images")
