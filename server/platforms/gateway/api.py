"""平台自身的接口，挂在 /api/platform 下。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from platforms import registry
from platforms.auth import service
from platforms.auth.permissions import PLATFORM_MENUS
from platforms.auth.principal import Principal, current_principal
from platforms.db import get_session

router = APIRouter()


@router.get("/modules")
async def list_modules(
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
):
    """前端启动后调这个接口拿到：已启用的模块、当前用户可见的菜单、以及权限码清单。

    菜单和权限只在后端 module.py 声明，前端不重复维护。
    """
    superuser = await service.is_superuser(session, principal)
    codes = set() if superuser else await service.permission_codes(session, principal)

    def visible(permission: str | None) -> bool:
        return superuser or permission is None or permission in codes

    modules = []
    for spec in registry.loaded_modules():
        menus = [
            {
                "title": menu.title,
                "path": menu.path,
                "icon": menu.icon,
                "order": menu.order,
                "parent": menu.parent,
                "permission": menu.permission,
            }
            for menu in sorted(spec.menus, key=lambda m: (m.order, m.path))
            if visible(menu.permission)
        ]
        modules.append({"name": spec.name, "title": spec.title, "version": spec.version, "menus": menus})

    platform_menus = [
        {
            "title": menu.title,
            "path": menu.path,
            "icon": menu.icon,
            "order": menu.order,
            "parent": menu.parent,
            "permission": menu.permission,
        }
        for menu in sorted(PLATFORM_MENUS, key=lambda m: (m.order, m.path))
        if visible(menu.permission)
    ]

    return {
        "modules": modules,
        "platform_menus": platform_menus,
        "permissions": sorted({p.code for p in registry.all_permissions()} if superuser else codes),
        "superuser": superuser,
    }
