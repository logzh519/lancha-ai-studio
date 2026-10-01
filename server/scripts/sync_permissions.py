"""把各模块 module.py 中声明的权限点同步到 platform.permission。

部署时在 alembic upgrade 之后执行：python scripts/sync_permissions.py
模块里删掉的权限点会连同角色绑定一起清理，所以这是唯一的权限点来源。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from platforms import registry  # noqa: E402
from platforms.auth.service import sync_permissions  # noqa: E402
from platforms.config import get_settings  # noqa: E402
from platforms.db import dispose_engine, get_engine  # noqa: E402
from platforms.gateway.loader import load_modules  # noqa: E402


async def main() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    registry.register(load_modules(get_settings().enabled_modules))
    declared = registry.all_permissions()

    async with AsyncSession(bind=get_engine()) as session:
        added, updated, removed = await sync_permissions(session, declared)
        await session.commit()
    await dispose_engine()
    print(f"权限点同步完成：新增 {added}，更新 {updated}，删除 {removed}，当前共 {len(declared)} 个")


if __name__ == "__main__":
    # psycopg 异步不支持 Windows 默认的 ProactorEventLoop，统一使用 SelectorEventLoop
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
