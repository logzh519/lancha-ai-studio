"""模块注册入口：模块元信息的唯一来源。"""

from modules.tiktok.api import router
from platforms.contract import MenuDef, ModuleSpec, PermissionDef

MODULE = ModuleSpec(
    name="tiktok",
    title="TikTok",
    version="0.1.0",
    router=router,
    permissions=(
        PermissionDef("tiktok:account:view", "查看 TikTok 账号"),
        PermissionDef("tiktok:account:create", "创建 TikTok 账号"),
    ),
    menus=(
        MenuDef("TikTok 账号", "/tiktok/accounts", icon="list", order=30, permission="tiktok:account:view"),
    ),
)
