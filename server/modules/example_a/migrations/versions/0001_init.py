"""Create or migrate the Example A item table.

Revision ID: 0001_example_init
Revises:
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_example_init"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mod_example_a"


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('mod_example_a.item') IS NULL
               AND to_regclass('mod_example.item') IS NOT NULL THEN
                ALTER TABLE mod_example.item SET SCHEMA mod_example_a;
            END IF;
        END $$;
        DROP TABLE IF EXISTS mod_example.alembic_version;
        DROP SCHEMA IF EXISTS mod_example;
        CREATE TABLE IF NOT EXISTS mod_example_a.item (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.drop_table("item", schema=SCHEMA)
