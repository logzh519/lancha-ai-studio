"""Create the script template table and drop the placeholder account table.

Revision ID: 0002_tiktok_script_template
Revises: 0001_tiktok_init
Create Date: 2026-10-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tiktok_script_template"
down_revision: Union[str, Sequence[str], None] = "0001_tiktok_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mod_tiktok"


def upgrade() -> None:
    op.create_table(
        "script_template",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("reference_video_url", sa.String(length=2048), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["platform.user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.drop_table("account", schema=SCHEMA)


def downgrade() -> None:
    op.create_table(
        "account",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.drop_table("script_template", schema=SCHEMA)
