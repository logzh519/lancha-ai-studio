"""Create the product master table.

Revision ID: 0003_tiktok_studio_product
Revises: 0002_tiktok_studio_template
Create Date: 2026-10-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_tiktok_studio_product"
down_revision: Union[str, Sequence[str], None] = "0002_tiktok_studio_template"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mod_tiktok_studio"


def _image_urls(name: str) -> sa.Column:
    return sa.Column(
        name, postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "product_master",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("asin", sa.String(length=32), nullable=True),
        sa.Column("color", sa.String(length=64), nullable=True),
        sa.Column("store", sa.String(length=128), nullable=True),
        sa.Column("pid", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("selling_points", sa.Text(), nullable=True),
        sa.Column("main_image_url", sa.String(length=2048), nullable=True),
        _image_urls("sub_images"),
        _image_urls("three_view_images"),
        _image_urls("three_view_reference_images"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["platform.user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("product_master", schema=SCHEMA)
