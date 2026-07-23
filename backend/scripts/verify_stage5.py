"""
verify_stage5.py — 阶段 5 验证脚本

用法：
    cd backend
    python -m scripts.verify_stage5

测试完整编排流程：TripRequest → trip_service → Itinerary
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import TripRequest
from app.services.trip_service import plan_trip

def main():
    print("=" * 60)
    print("阶段 5 验证：trip_service 主编排")
    print("=" * 60)

    # 构造一个完整的用户请求
    request = TripRequest(
        destination="大理",
        start_date=date(2025, 8, 1),
        end_date=date(2025, 8, 2),
        travelers=2,
        budget=3000,
        preferences=["自然风景", "美食"],
        pace="轻松",
        dietary_preferences=[],
        hotel_level="舒适型",
        special_notes="想看洱海日落",
    )

    print(f"\n用户请求:")
    print(f"  目的地: {request.destination}")
    print(f"  日期: {request.start_date} ~ {request.end_date}")
    print(f"  人数: {request.travelers}")
    print(f"  预算: {request.budget} 元")
    print(f"  偏好: {request.preferences}")
    print(f"  特殊要求: {request.special_notes}")

    # 调用主编排
    print(f"\n开始编排...")
    itinerary = plan_trip(request)

    # 打印结果
    print(f"\n{'=' * 60}")
    print(f"编排结果:")
    print(f"{'=' * 60}")
    print(f"\n  行程ID: {itinerary.trip_id}")
    print(f"  目的地: {itinerary.destination}")
    print(f"  概述: {itinerary.summary}")
    print(f"  总预算: {itinerary.estimated_budget} 元")
    print(f"  天数: {len(itinerary.days)}")

    for day in itinerary.days:
        print(f"\n  ── 第 {day.day_index} 天 ({day.date}) 主题: {day.theme} ──")
        for spot in day.spots:
            cost_str = f" ¥{spot.estimated_cost}" if spot.estimated_cost else ""
            print(f"    景点: {spot.name} ({spot.start_time}-{spot.end_time}){cost_str}")
        for meal in day.meals:
            print(f"    {meal.meal_type}: {meal.name} ¥{meal.estimated_cost}")
        if day.hotel:
            print(f"    住宿: {day.hotel.name} ¥{day.hotel.estimated_cost}")

    print(f"\n  预算明细:")
    bd = itinerary.budget_breakdown
    print(f"    交通 {bd.transport} + 住宿 {bd.hotel} + 餐饮 {bd.meals} "
          f"+ 门票 {bd.tickets} + 其他 {bd.other} = {bd.total}")

    print(f"\n  旅行建议:")
    for tip in itinerary.tips:
        print(f"    - {tip}")

    print(f"\n  攻略来源:")
    for note in itinerary.source_notes:
        print(f"    - {note}")

    if itinerary.token_usage:
        print(f"\n  Token统计:")
        print(f"    输入: {itinerary.token_usage.planner_prompt_tokens}")
        print(f"    输出: {itinerary.token_usage.planner_completion_tokens}")
        print(f"    总计: {itinerary.token_usage.total_tokens}")

    print(f"\n{'=' * 60}")
    print("验证完成！如果看到完整行程+来源说明+token统计，阶段5成功。")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()