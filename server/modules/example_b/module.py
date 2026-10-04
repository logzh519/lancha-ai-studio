"""Example B subscribes to the event published by Example A."""

from modules.example_b.api import router
from modules.example_b.service import on_item_created
from platforms.contract import MenuDef, ModuleSpec, PermissionDef

MODULE = ModuleSpec(
    name="example_b",
    title="Module System B",
    depends_on=("example_a",),
    router=router,
    permissions=(PermissionDef("example_b:event:view", "查看收到的事件"),),
    menus=(MenuDef("事件收件箱", "/example_b/events", icon="list", order=20, permission="example_b:event:view"),),
    subscriptions={"example_a.item_created": (on_item_created,)},
)