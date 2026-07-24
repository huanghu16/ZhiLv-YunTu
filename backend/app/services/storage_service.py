"""
storage_service.py — 行程存储服务

职责：
    封装所有数据库操作，对上层提供简洁的函数接口。

    - save_trip(itinerary): 保存行程
    - get_trip(trip_id): 按 ID 查询行程
    - list_trips(): 查询行程列表
    - delete_trip(trip_id): 删除行程
    - get_token_stats(): 查询 token 统计

上层（API 路由）只调这些函数，不直接操作数据库。
这就是"数据访问层"的职责分离。
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.config import SessionLocal
from app.models.db_models import TripRecord
from app.models.schemas import (
    Itinerary,
    TokenUsage,
    TripSummaryItem,
    TripTokenStatsItem,
)

def _get_db() -> Session:
    """获取数据库会话。调用方负责关闭。"""
    return SessionLocal()

def save_trip(itinerary: Itinerary) -> Itinerary:
    """
    保存行程到数据库。

    如果 trip_id 已存在则更新（upsert 语义）。
    """
    db = _get_db()
    try:
        # 序列化：Itinerary 对象 → JSON 字符串
        itinerary_json = itinerary.model_dump_json()

        # 查是否已存在
        existing = db.query(TripRecord).filter(TripRecord.trip_id == itinerary.trip_id).first()

        if existing:
            # 更新
            existing.destination = itinerary.destination
            existing.summary = itinerary.summary or ""
            existing.itinerary_json = itinerary_json
            existing.updated_at = datetime.utcnow()
        else:
            # 新建
            record = TripRecord(
                trip_id=itinerary.trip_id,
                destination=itinerary.destination,
                summary=itinerary.summary or "",
                itinerary_json=itinerary_json,
            )
            db.add(record)

        db.commit()
        print(f"[Storage] 行程已保存: {itinerary.trip_id} ({itinerary.destination})")
        return itinerary
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def get_trip(trip_id: str) -> Optional[Itinerary]:
    """
    按 ID 查询单个行程。

    返回 Itinerary 对象，找不到返回 None。
    """
    db = _get_db()
    try:
        record = db.query(TripRecord).filter(TripRecord.trip_id == trip_id).first()
        if not record:
            return None

        # 反序列化：JSON 字符串 → Itinerary 对象
        data = json.loads(record.itinerary_json)
        itinerary = Itinerary.model_validate(data)
        return itinerary
    finally:
        db.close()

def list_trips(
    destination: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[TripSummaryItem], int]:
    """
    查询行程列表。

    参数：
        destination: 按目的地筛选（可选）
        limit: 每页数量
        offset: 偏移量（分页用）

    返回：
        (items, total): 摘要列表 + 总数
    """
    db = _get_db()
    try:
        query = db.query(TripRecord)
        if destination:
            query = query.filter(TripRecord.destination == destination)

        total = query.count()
        records = (
            query.order_by(TripRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        items = [
            TripSummaryItem(
                trip_id=r.trip_id,
                destination=r.destination,
                summary=r.summary,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in records
        ]
        return items, total
    finally:
        db.close()

def delete_trip(trip_id: str) -> bool:
    """
    删除行程。成功返回 True，不存在返回 False。
    """
    db = _get_db()
    try:
        record = db.query(TripRecord).filter(TripRecord.trip_id == trip_id).first()
        if not record:
            return False
        db.delete(record)
        db.commit()
        print(f"[Storage] 行程已删除: {trip_id}")
        return True
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def get_token_stats() -> list[TripTokenStatsItem]:
    """
    查询所有行程的 token 统计。

    返回每条行程的 token 使用情况，用于成本分析。
    """
    db = _get_db()
    try:
        records = db.query(TripRecord).order_by(TripRecord.created_at.desc()).all()
        items = []
        for r in records:
            data = json.loads(r.itinerary_json)
            token_usage_data = data.get("token_usage")
            token_usage = TokenUsage.model_validate(token_usage_data) if token_usage_data else TokenUsage()
            items.append(
                TripTokenStatsItem(
                    trip_id=r.trip_id,
                    destination=r.destination,
                    token_usage=token_usage,
                )
            )
        return items
    finally:
        db.close()

# ── 导入放底部避免循环引用 ──────────────────────────────────
from datetime import datetime