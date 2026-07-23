"""
verify_stage4.py — 阶段 4 验证脚本

用法：
    cd backend
    python -m scripts.verify_stage4

测试 LLM 能否根据需求 + 攻略生成结构化行程。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.rag.retriever import retrieve
from app.agents.trip_planner_agent import generate_itinerary

def main():
    print("=" * 60)
    print("阶段 4 验证：LLM 结构化行程生成")
    print("=" * 60)

    # 1. 先用阶段 3 的检索器获取攻略
    print("\n[1/3] RAG 检索攻略...")
    results = retrieve(
        user_input="想看日落，吃当地美食",
        destination="大理",
        top_k=3,
    )

    # 拼接攻略文本
    rag_context = "\n\n".join(
        f"【{r['metadata'].get('heading', '')}】\n{r['content']}"
        for r in results
    )
    print(f"  检索到 {len(results)} 条攻略:")
    for r in results:
        print(f"    - {r['metadata'].get('heading', '')} (score={r['rerank_score']})")

    # 2. 调用 LLM 生成行程
    print("\n[2/3] 调用 LLM 生成行程...")
    itinerary, token_usage = generate_itinerary(
        destination="大理",
        start_date=date(2025, 8, 1),
        end_date=date(2025, 8, 3),
        travelers=2,
        budget=5000,
        preferences=["自然风景", "美食"],
        pace="适中",
        hotel_level="舒适型",
        special_notes="想看洱海日落",
        rag_context=rag_context,
    )

    # 3. 打印结果
    print("\n[3/3] 生成结果:")
    print(f"\n  行程ID: {itinerary.trip_id}")
    print(f"  目的地: {itinerary.destination}")
    print(f"  概述: {itinerary.summary}")
    print(f"  总预算: {itinerary.estimated_budget} 元")
    print(f"  预算明细: 交通{itinerary.budget_breakdown.transport} / "
          f"住宿{itinerary.budget_breakdown.hotel} / "
          f"餐饮{itinerary.budget_breakdown.meals} / "
          f"门票{itinerary.budget_breakdown.tickets}")
    print(f"  天数: {len(itinerary.days)}")

    for day in itinerary.days:
        print(f"\n  ── 第 {day.day_index} 天 ({day.date}) 主题: {day.theme} ──")
        for spot in day.spots:
            print(f"    景点: {spot.name} ({spot.start_time}-{spot.end_time}) ¥{spot.estimated_cost}")
            if spot.description:
                print(f"      {spot.description[:50]}")
        for meal in day.meals:
            print(f"    {meal.meal_type}: {meal.name} ¥{meal.estimated_cost}")
        if day.hotel:
            print(f"    住宿: {day.hotel.name} ¥{day.hotel.estimated_cost}")
        for t in day.transport:
            print(f"    交通: {t.mode} {t.from_place}→{t.to_place} ¥{t.estimated_cost}")

    print(f"\n  旅行建议:")
    for tip in itinerary.tips:
        print(f"    - {tip}")

    print(f"\n  Token 消耗:")
    print(f"    输入: {token_usage.planner_prompt_tokens}")
    print(f"    输出: {token_usage.planner_completion_tokens}")
    print(f"    总计: {token_usage.total_tokens}")

    print("\n" + "=" * 60)
    print("验证完成！如果看到结构化行程，说明阶段 4 成功。")
    print("=" * 60)

if __name__ == "__main__":
    main()