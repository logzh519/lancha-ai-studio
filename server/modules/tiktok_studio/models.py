"""模块的表全部建在自己的 schema（mod_tiktok_studio）下，不允许出现指向其他模块 schema 的外键。"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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


class Batch(Base):
    """一次运营确认的批量视频任务。"""

    __tablename__ = "batch"
    __table_args__ = (
        UniqueConstraint("created_by", "request_id", name="uq_batch_created_request"),
        Index("ix_batch_created_by", "created_by", "created_at"),
        Index("ix_batch_status", "status"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    pipeline_key: Mapped[str] = mapped_column(String(64), default="video_gen_15s")
    request_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    review_overrides: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), default="running")
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey(AppUser.id, ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Task(Base):
    """批次内单个 ASIN 对应的视频任务。"""

    __tablename__ = "task"
    __table_args__ = (
        UniqueConstraint("batch_id", "biz_key", name="uq_task_batch_bizkey"),
        Index("ix_task_batch", "batch_id"),
        Index("ix_task_created_by_status", "created_by", "status"),
        Index("ix_task_biz_key", "biz_key"),
        Index(
            "ix_task_admit",
            "status",
            "priority",
            "created_at",
            postgresql_where=text("status = 'admitted_pending'"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.batch.id", ondelete="CASCADE")
    )
    pipeline_key: Mapped[str] = mapped_column(String(64), default="video_gen_15s")
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey(AppUser.id, ondelete="RESTRICT"))
    biz_key: Mapped[str] = mapped_column(String(255))
    context: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(24), default="admitted_pending")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    progress: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
