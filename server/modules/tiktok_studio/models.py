"""模块的表全部建在自己的 schema（mod_tiktok_studio）下，不允许出现指向其他模块 schema 的外键。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
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
