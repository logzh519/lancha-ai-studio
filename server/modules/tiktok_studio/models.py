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
    """商品资产。主图为单个 URL，其余图片字段为 URL 数组。"""

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
    main_image_url: Mapped[str | None] = mapped_column(String(2048))
    sub_images: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    three_view_images: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    three_view_reference_images: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey(AppUser.id, ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
