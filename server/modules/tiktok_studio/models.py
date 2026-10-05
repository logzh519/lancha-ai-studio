"""模块的表全部建在自己的 schema（mod_tiktok_studio）下，不允许出现指向其他模块 schema 的外键。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from platforms.auth.models import AppUser
from platforms.db import Base, module_schema

SCHEMA = module_schema("tiktok_studio")


class ScriptTemplate(Base):
    """爆款视频脚本模板。"""

    __tablename__ = "script_template"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(16))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    version: Mapped[str] = mapped_column(String(32))
    reference_video_url: Mapped[str | None] = mapped_column(String(2048))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey(AppUser.id, ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProductMaster(Base):
    """商品资产。图片字段存 schemas.StoredObject 结构（key、url、type），主图为单个对象，其余为对象数组。"""

    __tablename__ = "product_master"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64))
    asin: Mapped[str | None] = mapped_column(String(32))
    color: Mapped[str | None] = mapped_column(String(64))
    store: Mapped[str | None] = mapped_column(String(128))
    pid: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    selling_points: Mapped[str | None] = mapped_column(Text)
    main_image: Mapped[dict | None] = mapped_column(JSONB)
    sub_images: Mapped[list[dict]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    three_view_images: Mapped[list[dict]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    three_view_reference_images: Mapped[list[dict]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    # 侧面参考图类型（view_select 的 side_kind），生成三视图时需要；无侧面为 none
    three_view_side_kind: Mapped[str | None] = mapped_column(String(32))
    # 自动导入的三个后台阶段，取值见 schemas.ImportStatus；手工新建的商品为 None
    crawl_status: Mapped[str | None] = mapped_column(String(16))
    crawl_error: Mapped[str | None] = mapped_column(Text)
    view_status: Mapped[str | None] = mapped_column(String(16))
    view_error: Mapped[str | None] = mapped_column(Text)
    gen_status: Mapped[str | None] = mapped_column(String(16))
    gen_error: Mapped[str | None] = mapped_column(Text)
    # 失败阶段的现场：{crawl|view|gen: {input, output, error_code, error_message}}，该阶段成功后移除
    import_trace: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey(AppUser.id, ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
