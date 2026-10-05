"""Store product master images as {key, url, type} objects.

main_image_url (string) is replaced by main_image (jsonb object); the three image arrays change
from URL strings to objects. Existing URLs are backfilled as external links (key null), so their
storage objects are not cleaned up when records are deleted.

Revision ID: 0006_tiktok_studio_object
Revises: 0005_tiktok_studio_gen
Create Date: 2026-10-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_tiktok_studio_object"
down_revision: Union[str, Sequence[str], None] = "0005_tiktok_studio_gen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "mod_tiktok_studio"
TABLE = f"{SCHEMA}.product_master"
LIST_COLUMNS = ("sub_images", "three_view_images", "three_view_reference_images")


def upgrade() -> None:
    op.add_column("product_master", sa.Column("main_image", postgresql.JSONB(), nullable=True), schema=SCHEMA)
    op.execute(
        f"UPDATE {TABLE} SET main_image = jsonb_build_object('key', NULL, 'url', main_image_url, 'type', 'external') "
        "WHERE main_image_url IS NOT NULL"
    )
    for column in LIST_COLUMNS:
        op.execute(
            f"UPDATE {TABLE} SET {column} = ("
            "SELECT COALESCE(jsonb_agg(jsonb_build_object('key', NULL, 'url', t.value, 'type', 'external') "
            "ORDER BY t.ord), '[]'::jsonb) "
            f"FROM jsonb_array_elements_text({column}) WITH ORDINALITY AS t(value, ord)) "
            f"WHERE jsonb_typeof({column} -> 0) = 'string'"
        )
    op.drop_column("product_master", "main_image_url", schema=SCHEMA)


def downgrade() -> None:
    op.add_column("product_master", sa.Column("main_image_url", sa.String(length=2048), nullable=True), schema=SCHEMA)
    op.execute(f"UPDATE {TABLE} SET main_image_url = main_image ->> 'url'")
    for column in LIST_COLUMNS:
        op.execute(
            f"UPDATE {TABLE} SET {column} = ("
            "SELECT COALESCE(jsonb_agg(t.value -> 'url' ORDER BY t.ord), '[]'::jsonb) "
            f"FROM jsonb_array_elements({column}) WITH ORDINALITY AS t(value, ord) "
            "WHERE t.value ->> 'url' IS NOT NULL) "
            f"WHERE jsonb_typeof({column} -> 0) = 'object'"
        )
    op.drop_column("product_master", "main_image", schema=SCHEMA)
