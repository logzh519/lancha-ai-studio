"""Record failed import stage input, output and error on product master.

Revision ID: 0007_tiktok_studio_trace
Revises: 0006_tiktok_studio_object
Create Date: 2026-10-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_tiktok_studio_trace"
down_revision: Union[str, Sequence[str], None] = "0006_tiktok_studio_object"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mod_tiktok_studio"


def upgrade() -> None:
    op.add_column(
        "product_master",
        sa.Column(
            "import_trace", postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("product_master", "import_trace", schema=SCHEMA)
