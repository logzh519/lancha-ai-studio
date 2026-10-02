"""认证：外部身份、会话与 OAuth state

Revision ID: 0002_auth_session
Revises: 0001_rbac

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_session"
down_revision: Union[str, Sequence[str], None] = "0001_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "platform"


def upgrade() -> None:
    op.create_table(
        "user_identity",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("union_id", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("avatar_url", sa.String(length=512), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_user_identity_provider_external"),
        schema=SCHEMA,
    )
    op.create_index("ix_platform_user_identity_user_id", "user_identity", ["user_id"], schema=SCHEMA)

    op.create_table(
        "user_session",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
        schema=SCHEMA,
    )
    op.create_index("ix_platform_user_session_user_id", "user_session", ["user_id"], schema=SCHEMA)
    op.create_index("ix_platform_user_session_expires_at", "user_session", ["expires_at"], schema=SCHEMA)

    op.create_table(
        "oauth_state",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("state_hash"),
        schema=SCHEMA,
    )
    op.create_index("ix_platform_oauth_state_expires_at", "oauth_state", ["expires_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_platform_oauth_state_expires_at", table_name="oauth_state", schema=SCHEMA)
    op.drop_table("oauth_state", schema=SCHEMA)
    op.drop_index("ix_platform_user_session_expires_at", table_name="user_session", schema=SCHEMA)
    op.drop_index("ix_platform_user_session_user_id", table_name="user_session", schema=SCHEMA)
    op.drop_table("user_session", schema=SCHEMA)
    op.drop_index("ix_platform_user_identity_user_id", table_name="user_identity", schema=SCHEMA)
    op.drop_table("user_identity", schema=SCHEMA)
