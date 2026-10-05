"""Add three-view generation stage columns to product master.

Revision ID: 0005_tiktok_studio_gen
Revises: 0004_tiktok_studio_import
Create Date: 2026-10-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_tiktok_studio_gen"
down_revision: Union[str, Sequence[str], None] = "0004_tiktok_studio_import"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mod_tiktok_studio"


def upgrade() -> None:
    op.add_column(
        "product_master", sa.Column("three_view_side_kind", sa.String(length=32), nullable=True), schema=SCHEMA,
    )
    op.add_column("product_master", sa.Column("gen_status", sa.String(length=16), nullable=True), schema=SCHEMA)
    op.add_column("product_master", sa.Column("gen_error", sa.Text(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("product_master", "gen_error", schema=SCHEMA)
    op.drop_column("product_master", "gen_status", schema=SCHEMA)
    op.drop_column("product_master", "three_view_side_kind", schema=SCHEMA)
