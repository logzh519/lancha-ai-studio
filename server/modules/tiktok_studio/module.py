"""模块注册入口：模块元信息的唯一来源。"""

from modules.tiktok_studio.api import router
from platforms.contract import MenuDef, ModuleSpec, PermissionDef

MODULE = ModuleSpec(
    name="tiktok_studio",
    title="TikTok Studio",
    version="0.1.0",
    router=router,
    permissions=(
        PermissionDef("tiktok_studio:script_template:view", "查看爆款脚本"),
        PermissionDef("tiktok_studio:script_template:create", "新建爆款脚本"),
        PermissionDef("tiktok_studio:script_template:update", "修改爆款脚本"),
        PermissionDef("tiktok_studio:script_template:delete", "删除爆款脚本"),
    ),
    menus=(
        MenuDef(
            "爆款脚本库",
            "/tiktok_studio/script-templates",
            icon="list",
            order=30,
            permission="tiktok_studio:script_template:view",
        ),
    ),
)
