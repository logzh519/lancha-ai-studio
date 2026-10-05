"""Add task and batch lifecycle fields.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mod_tiktok_studio"


def upgrade() -> None:
    op.add_column(
        "batch",
        sa.Column(
            "review_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column("batch", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("task", sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("task", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("task", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("task", "finished_at", schema=SCHEMA)
    op.drop_column("task", "started_at", schema=SCHEMA)
    op.drop_column("task", "admitted_at", schema=SCHEMA)
    op.drop_column("batch", "finished_at", schema=SCHEMA)
    op.drop_column("batch", "review_overrides", schema=SCHEMA)
