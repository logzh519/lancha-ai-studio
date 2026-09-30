"""数据库接入：全平台一个 PostgreSQL 库，按 schema 隔离。

平台表建在 platform schema，模块表建在 mod_<模块名> schema。
模块只能读写自己的 schema；跨模块取数走对方 contract.py 或事件，禁止跨 schema JOIN 与外键。
唯一的例外是可以引用 platform.app_user.id。
"""

from collections.abc import AsyncIterator

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from platforms.config import get_settings

PLATFORM_SCHEMA = "platform"


def module_schema(module: str) -> str:
    """模块的专属 schema 名。"""
    return f"mod_{module}"


class Base(DeclarativeBase):
    """全平台共用一份 MetaData：各表用 __table_args__ = {"schema": ...} 声明归属。"""


def build_url() -> URL:
    settings = get_settings()
    return URL.create(
        "postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password,
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """返回进程内共享的 AsyncEngine（首次调用时创建）。"""
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            build_url(),
            pool_pre_ping=True,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            connect_args={"connect_timeout": 10},
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：一个请求一个事务，正常返回时提交，抛异常时回滚。"""
    get_engine()
    assert _session_factory is not None
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """释放连接池（进程退出前调用）。"""
    global _engine, _session_factory
    engine, _engine, _session_factory = _engine, None, None
    if engine is not None:
        await engine.dispose()
