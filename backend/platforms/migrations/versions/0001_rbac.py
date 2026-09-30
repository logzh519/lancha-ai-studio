"""RBAC 基础表

Revision ID: 0001_rbac
Revises:
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_rbac"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "platform"


def _timestamps() -> list[sa.Column]:
    # Column 对象不能在多张表之间复用，每张表都要新建一组
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        schema=SCHEMA,
    )
    op.create_table(
        "role",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        schema=SCHEMA,
    )
    op.create_table(
        "permission",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        schema=SCHEMA,
    )
    # 索引名要和 SQLAlchemy 对带 schema 的表生成的名字一致（含 schema 前缀），否则 alembic check 会一直有 diff
    op.create_index("ix_platform_permission_module", "permission", ["module"], schema=SCHEMA)

    op.create_table(
        "user_role",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], [f"{SCHEMA}.role.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
        schema=SCHEMA,
    )
    op.create_table(
        "role_permission",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], [f"{SCHEMA}.role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], [f"{SCHEMA}.permission.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("role_permission", schema=SCHEMA)
    op.drop_table("user_role", schema=SCHEMA)
    op.drop_index("ix_platform_permission_module", table_name="permission", schema=SCHEMA)
    op.drop_table("permission", schema=SCHEMA)
    op.drop_table("role", schema=SCHEMA)
    op.drop_table("app_user", schema=SCHEMA)
