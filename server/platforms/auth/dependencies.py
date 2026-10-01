"""接口级权限校验：路由上写 dependencies=[Depends(require("example:item:create"))]。

权限码必须在本模块 module.py 的 permissions 中声明过，否则 loader 在启动时就会拒绝加载。
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from platforms.auth import service
from platforms.auth.principal import Principal, current_principal
from platforms.db import get_session


def require(*codes: str):
    """要求主体同时具备全部给定权限码。"""
    if not codes:
        raise ValueError("require() 至少需要一个权限码")

    async def dependency(
        principal: Principal = Depends(current_principal),
        session: AsyncSession = Depends(get_session),
    ) -> Principal:
        if await service.is_superuser(session, principal):
            return principal
        missing = set(codes) - await service.permission_codes(session, principal)
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"缺少权限：{'、'.join(sorted(missing))}")
        return principal

    return dependency
