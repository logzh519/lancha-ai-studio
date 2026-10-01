"""所有迁移分支共用的 env.py。

分支由 alembic -n <分支名> 选择：platform 对应平台表，其余为模块名。
每个分支只迁移自己 schema 下的表，alembic_version 也建在该 schema 里，分支之间完全独立。
"""

import importlib
import importlib.util
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool, text

from alembic import context
from platforms.db import PLATFORM_SCHEMA, Base, build_url, module_schema

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

branch = config.config_ini_section
if branch == "alembic":
    raise SystemExit("请用 alembic -n <分支名> 指定分支，例如：alembic -n platform upgrade head")


def _import_models() -> None:
    """ORM 模型必须先导入注册到 Base.metadata，autogenerate 才能比对出差异。"""
    if branch == PLATFORM_SCHEMA:
        for path in sorted(Path(__file__).resolve().parent.parent.glob("platforms/*/models.py")):
            importlib.import_module(f"platforms.{path.parent.name}.models")
    elif importlib.util.find_spec(f"modules.{branch}.models"):
        importlib.import_module(f"modules.{branch}.models")


target_schema = PLATFORM_SCHEMA if branch == PLATFORM_SCHEMA else module_schema(branch)
_import_models()


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """只比对本分支 schema 下的表，别的模块的表当作不存在。"""
    if type_ == "table":
        return obj.schema == target_schema
    return True


def _context_options() -> dict:
    return {
        "target_metadata": Base.metadata,
        "version_table_schema": target_schema,
        "include_schemas": True,
        "include_object": include_object,
    }


def run_migrations_offline() -> None:
    context.configure(
        url=build_url().render_as_string(hide_password=False),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_context_options(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(build_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{target_schema}"'))
        connection.commit()
        context.configure(connection=connection, **_context_options())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
