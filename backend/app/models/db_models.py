"""
db_models.py — 数据库模型（SQLAlchemy ORM）

职责：
    定义 SQLite 数据库的表结构。

设计决策：为什么不拆成多张表？
→ 行程数据（Itinerary → DayPlan → SpotItem/MealItem...）嵌套很深，
  如果拆成 days、spots、meals、hotels、transport 五张表，
  查询一个行程要 JOIN 5 次，写入要 INSERT 多行，复杂且慢。
  而行程总是"整体读取、整体保存"，不需要跨行程关联查询，
  所以用一行存一个完整行程，itinerary_json 列存整个 JSON。

这就是"聚合根"模式：Itinerary 是一个聚合，整体存取。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text

from app.config import Base

class TripRecord(Base):
    """
    行程记录表（对应 SQLite 的 trips 表）。

    一行 = 一个完整行程。
    """
    __tablename__ = "trips"

    # 主键：行程唯一 ID，和 Itinerary.trip_id 一致
    trip_id = Column(String(64), primary_key=True, comment="行程唯一ID")

    # 冗余字段：把 destination 和 summary 单独存一列，
    # 这样查列表时不用解析 JSON 就能显示摘要
    destination = Column(String(100), nullable=False, comment="目的地")
    summary = Column(String(500), nullable=False, default="", comment="行程概述")

    # 核心：完整行程的 JSON 字符串
    # 存 Itinerary.model_dump_json() 的结果
    itinerary_json = Column(Text, nullable=False, comment="完整行程JSON")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 索引：按目的地查询时加速
    __table_args__ = (
        Index("idx_trips_destination", "destination"),
        Index("idx_trips_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<TripRecord(trip_id={self.trip_id}, destination={self.destination})>"