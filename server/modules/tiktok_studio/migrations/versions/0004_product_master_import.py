"""Add auto-import stage status columns to product master.

Revision ID: 0004_tiktok_studio_import
Revises: 0003_tiktok_studio_product
Create Date: 2026-10-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_tiktok_studio_import"
down_revision: Union[str, Sequence[str], None] = "0003_tiktok_studio_product"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mod_tiktok_studio"


def upgrade() -> None:
    op.add_column("product_master", sa.Column("crawl_status", sa.String(length=16), nullable=True), schema=SCHEMA)
    op.add_column("product_master", sa.Column("crawl_error", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column("product_master", sa.Column("view_status", sa.String(length=16), nullable=True), schema=SCHEMA)
    op.add_column("product_master", sa.Column("view_error", sa.Text(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("product_master", "view_error", schema=SCHEMA)
    op.drop_column("product_master", "view_status", schema=SCHEMA)
    op.drop_column("product_master", "crawl_error", schema=SCHEMA)
    op.drop_column("product_master", "crawl_status", schema=SCHEMA)
