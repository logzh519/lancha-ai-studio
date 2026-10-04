"""模块的表全部建在自己的 schema（mod_example_a）下，不允许出现指向其他模块 schema 的外键。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from platforms.db import Base, module_schema

SCHEMA = module_schema("example_a")


class Item(Base):
    __tablename__ = "item"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
