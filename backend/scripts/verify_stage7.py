"""
verify_stage7.py — 阶段 7 验证脚本

用法：
    cd backend
    python -m scripts.verify_stage7

测试：保存 → 查询列表 → 查询详情 → token统计 → 删除
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import engine
from app.models.db_models import TripRecord, Base
from app.models.schemas import TripRequest, Itinerary, BudgetBreakdown, DayPlan
from app.services.storage_service import (
    save_trip,
    get_trip,
    list_trips,
    delete_trip,
    get_token_stats,
)

def make_test_itinerary(trip_id: str, destination: str) -> Itinerary:
    """构造一个测试行程（不调用 LLM，直接拼数据）。"""
    return Itinerary(
        trip_id=trip_id,
        destination=destination,
        summary=f"{destination}两日游测试行程",
        days=[
            DayPlan(
                day_index=1,
                date=date(2025, 8, 1),
                theme="第一天",
                spots=[],
                meals=[],
                transport=[],
                notes=[],
            )
        ],
        estimated_budget=2000,
        budget_breakdown=BudgetBreakdown(
            transport=200, hotel=800, meals=500, tickets=300, other=200, total=2000
        ),
        tips=["测试建议"],
        source_notes=["测试来源"],
    )

def main():
    print("=" * 60)
    print("阶段 7 验证：SQLite 持久化")
    print("=" * 60)

    # 0. 建表
    print("\n[0] 创建数据库表...")
    Base.metadata.create_all(bind=engine)
    print("  表创建成功（如已存在则跳过）")

    # 1. 保存
    print("\n[1/5] 保存行程...")
    trip1 = make_test_itinerary("test_trip_001", "大理")
    trip2 = make_test_itinerary("test_trip_002", "丽江")
    save_trip(trip1)
    save_trip(trip2)
    print("  保存了 2 个测试行程")

    # 2. 查询列表
    print("\n[2/5] 查询行程列表...")
    items, total = list_trips()
    print(f"  总数: {total}")
    for item in items:
        print(f"  - {item.trip_id}: {item.destination} ({item.summary})")

    # 3. 查询详情
    print("\n[3/5] 查询单个行程...")
    itinerary = get_trip("test_trip_001")
    if itinerary:
        print(f"  查询成功: {itinerary.trip_id}")
        print(f"  目的地: {itinerary.destination}")
        print(f"  概述: {itinerary.summary}")
        print(f"  天数: {len(itinerary.days)}")
    else:
        print("  查询失败：行程不存在")

    # 4. token 统计
    print("\n[4/5] token 统计...")
    stats = get_token_stats()
    print(f"  行程数: {len(stats)}")

    # 5. 删除
    print("\n[5/5] 删除行程...")
    success1 = delete_trip("test_trip_001")
    success2 = delete_trip("test_trip_002")
    print(f"  删除 test_trip_001: {'成功' if success1 else '失败'}")
    print(f"  删除 test_trip_002: {'成功' if success2 else '失败'}")

    # 验证删除后列表为空（或只剩之前生成的真实行程）
    items_after, total_after = list_trips()
    print(f"  删除后剩余行程数: {total_after}")

    print("\n" + "=" * 60)
    print("验证完成！5 项操作都成功说明阶段 7 通过。")
    print("=" * 60)

if __name__ == "__main__":
    main()