"""修正 oauth_state 表缺失 nonce_hash 列。

Revision ID: 0003_fix_oauth_state_nonce_hash
Revises: 0002_auth_session
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_fix_oauth_state_nonce_hash"
down_revision: Union[str, Sequence[str], None] = "0002_auth_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "platform"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [column["name"] for column in inspector.get_columns("oauth_state", schema=SCHEMA)]

    if "nonce_hash" not in columns:
        op.add_column(
            "oauth_state",
            sa.Column("nonce_hash", sa.String(length=64), nullable=True),
            schema=SCHEMA,
        )
        op.execute(
            sa.text(f'UPDATE "{SCHEMA}"."oauth_state" SET nonce_hash = state_hash WHERE nonce_hash IS NULL')
        )
        op.alter_column("oauth_state", "nonce_hash", nullable=False, schema=SCHEMA)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [column["name"] for column in inspector.get_columns("oauth_state", schema=SCHEMA)]

    if "nonce_hash" in columns:
        op.drop_column("oauth_state", "nonce_hash", schema=SCHEMA)
