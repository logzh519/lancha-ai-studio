"""测试公共装置。

安全约束：测试只连 <库名>_test 库，且在任何 Engine 创建之前把库名改掉，避免误删开发数据。
连不上 PostgreSQL 时，标了 @pytest.mark.db 的用例自动跳过，其余用例照常执行。
"""

import asyncio
import importlib
import importlib.util
import os

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.config import get_settings
from platforms.db import PLATFORM_SCHEMA, Base, dispose_engine, get_engine, module_schema
from platforms.gateway.loader import discover_module_names

_settings = get_settings()
if not _settings.postgres_db.endswith("_test"):
    os.environ["POSTGRES_DB"] = f"{_settings.postgres_db}_test"
    get_settings.cache_clear()


def pytest_asyncio_loop_factories(config, item):
    # psycopg 异步不支持 Windows 默认的 ProactorEventLoop，统一使用 SelectorEventLoop
    return {"selector": asyncio.SelectorEventLoop}


def _maintenance_dsn() -> dict:
    settings = get_settings()
    return {
        "host": settings.postgres_host,
        "port": settings.postgres_port,
        "user": settings.postgres_user,
        "password": settings.postgres_password,
        "dbname": "postgres",
        "connect_timeout": 3,
    }


def pytest_collection_modifyitems(config, items):
    try:
        psycopg.connect(**_maintenance_dsn()).close()
        return
    except Exception as exc:
        skip = pytest.mark.skip(reason=f"PostgreSQL 不可用，跳过 db 用例：{exc}")
        for item in items:
            if "db" in item.keywords:
                item.add_marker(skip)


def _create_test_database() -> None:
    settings = get_settings()
    if not settings.postgres_db.endswith("_test"):
        raise RuntimeError(f"拒绝在非测试库 {settings.postgres_db} 上运行测试（库名须以 _test 结尾）")
    with psycopg.connect(**_maintenance_dsn(), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.postgres_db,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.postgres_db)))


def _import_all_models() -> list[str]:
    """导入平台与各模块的模型，返回需要建的 schema 列表。"""
    importlib.import_module("platforms.auth.models")
    schemas = [PLATFORM_SCHEMA]
    for name in discover_module_names():
        if importlib.util.find_spec(f"modules.{name}.models"):
            importlib.import_module(f"modules.{name}.models")
            schemas.append(module_schema(name))
    return schemas


@pytest.fixture(scope="session")
async def db_ready():
    """建好测试库与全部 schema、表。

    这里直接用 metadata.create_all 而不是跑 alembic：测试关心的是模型行为，
    迁移脚本的正确性由部署前的 alembic upgrade 保证。
    """
    _create_test_database()
    schemas = _import_all_models()
    async with get_engine().begin() as conn:
        for schema in schemas:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture
async def session(db_ready):
    """每个用例一个事务，结束后回滚，用例之间互不影响。"""
    async with get_engine().connect() as conn:
        transaction = await conn.begin()
        db_session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield db_session
        finally:
            await db_session.close()
            await transaction.rollback()


@pytest.fixture(autouse=True)
def restore_principal_provider():
    """create_app(auth_mode="feishu") 会全局替换 provider，用例之间必须还原，否则互相污染。"""
    from platforms.auth.principal import reset_principal_provider

    yield
    reset_principal_provider()
