"""
trip_planner_agent.py — 行程规划 Agent

职责：
1. 把用户需求 + RAG 攻略 + 格式约束组装成 Prompt
2. 调用 LLM 生成结构化行程（JSON 格式）
3. 解析 JSON → 转成 Pydantic Itinerary 对象
4. 记录 token 消耗

这是"Agent 层"的核心。严格说它是"LLM 调用 + 输出解析"，
不是自主决策的 Agent（那是阶段5的 trip_service 做编排）。

Prompt 工程的关键：
- System Prompt 定义角色和输出格式
- Human Prompt 提供具体需求和参考资料
- 明确要求输出 JSON，否则 LLM 会返回自然语言
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date as DateType, timedelta

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm_client import get_llm_client
from app.models.schemas import (
    BudgetBreakdown,
    DayPlan,
    Itinerary,
    TokenUsage,
)

# ─── Prompt 模板 ────────────────────────────────────────────

SYSTEM_PROMPT = """你是一位专业的旅行规划师，擅长根据用户需求设计详细、合理的旅行行程。

你的任务：
1. 根据用户的目的地、日期、人数、预算和偏好，生成逐日行程
2. 参考提供的攻略信息，确保景点、美食、交通安排合理
3. 预算分配要合理，不要超出用户总预算
4. 每天安排 2-4 个景点，不要太紧凑

输出要求（非常重要）：
你必须输出一个合法的 JSON 对象，不要输出任何其他文字。
JSON 格式如下：

{
  "summary": "整趟行程的概述，1-2句话",
  "days": [
    {
      "day_index": 1,
      "date": "2024-07-01",
      "theme": "当天主题",
      "spots": [
        {
          "name": "景点名称",
          "start_time": "09:00",
          "end_time": "11:00",
          "description": "景点说明",
          "estimated_cost": 50.0,
          "location": "位置描述"
        }
      ],
      "meals": [
        {
          "name": "餐厅名称",
          "meal_type": "午餐",
          "estimated_cost": 60.0,
          "notes": "补充说明"
        }
      ],
      "hotel": {
        "name": "酒店名称",
        "level": "舒适型",
        "estimated_cost": 300.0,
        "location": "位置"
      },
      "transport": [
        {
          "mode": "打车",
          "from_place": "出发地",
          "to_place": "目的地",
          "estimated_cost": 30.0,
          "duration": "30分钟"
        }
      ],
      "notes": ["当天注意事项"]
    }
  ],
  "estimated_budget": 3000.0,
  "budget_breakdown": {
    "transport": 500.0,
    "hotel": 1000.0,
    "meals": 800.0,
    "tickets": 400.0,
    "other": 300.0,
    "total": 3000.0
  },
  "tips": ["旅行建议1", "旅行建议2"]
}

注意事项：
- date 格式为 "YYYY-MM-DD"
- estimated_cost 单位为元，必须 >= 0
- meal_type 只能是 "早餐"、"午餐" 或 "晚餐"
- budget_breakdown.total 必须等于各分项之和
- 只输出 JSON，不要输出 markdown 代码块标记"""

def _build_human_prompt(
    destination: str,
    start_date: DateType,
    end_date: DateType,
    travelers: int,
    budget: float,
    preferences: list[str],
    pace: str | None,
    dietary_preferences: list[str],
    hotel_level: str | None,
    special_notes: str | None,
    rag_context: str,
) -> str:
    """
    组装用户消息（Human Message）。

    把用户需求和 RAG 攻略拼接成一段清晰的文本。
    """
    # 计算天数
    num_days = (end_date - start_date).days + 1

    parts = [
        f"目的地：{destination}",
        f"出行日期：{start_date} 至 {end_date}，共 {num_days} 天",
        f"出行人数：{travelers} 人",
        f"总预算：{budget} 元",
    ]

    if preferences:
        parts.append(f"偏好：{', '.join(preferences)}")
    if pace:
        parts.append(f"节奏：{pace}")
    if dietary_preferences:
        parts.append(f"饮食偏好：{', '.join(dietary_preferences)}")
    if hotel_level:
        parts.append(f"酒店档次：{hotel_level}")
    if special_notes:
        parts.append(f"特殊要求：{special_notes}")

    parts.append(f"\n以下是{destination}的攻略参考资料：")
    parts.append(rag_context)
    parts.append("\n请根据以上信息生成行程，只输出 JSON。")

    return "\n".join(parts)

def _extract_json(text: str) -> dict:
    """
    从 LLM 输出中提取 JSON。

    LLM 有时会输出 markdown 代码块包裹的 JSON（```json ... ```），
    需要去掉代码块标记再解析。
    """
    # 尝试去掉 markdown 代码块标记
    # ```json\n{...}\n```  →  {...}
    text = text.strip()
    if text.startswith("```"):
        # 去掉开头的 ```json 或 ```
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        # 去掉结尾的 ```
        text = re.sub(r"\n?```\s*$", "", text)

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 如果直接解析失败，尝试提取第一个 { 到最后一个 } 之间的内容
    # 这处理 LLM 在 JSON 前后加了多余文字的情况
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从 LLM 输出中解析 JSON。输出前 200 字符：{text[:200]}")

def generate_itinerary(
    destination: str,
    start_date: DateType,
    end_date: DateType,
    travelers: int,
    budget: float,
    preferences: list[str] | None = None,
    pace: str | None = None,
    dietary_preferences: list[str] | None = None,
    hotel_level: str | None = None,
    special_notes: str | None = None,
    rag_context: str = "",
) -> tuple[Itinerary, TokenUsage]:
    """
    调用 LLM 生成结构化行程。

    参数：
        与 TripRequest 的字段一一对应
        rag_context: RAG 检索到的攻略文本（拼接好的字符串）

    返回：
        (itinerary, token_usage)
        - itinerary: 解析后的 Itinerary 对象
        - token_usage: 本次 LLM 调用的 token 消耗
    """
    # 1. 组装 Prompt
    human_prompt = _build_human_prompt(
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        travelers=travelers,
        budget=budget,
        preferences=preferences or [],
        pace=pace,
        dietary_preferences=dietary_preferences or [],
        hotel_level=hotel_level,
        special_notes=special_notes,
        rag_context=rag_context,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_prompt),
    ]

    # 2. 调用 LLM
    print(f"[Agent] 正在调用 LLM 生成行程（模型: {LLM_MODEL}）...")
    client = get_llm_client()
    content, token_info = client.invoke(messages)

    # 3. 解析 JSON
    print("[Agent] 正在解析 LLM 输出...")
    raw_data = _extract_json(content)

    # 4. 生成 trip_id 并组装 Itinerary
    trip_id = f"trip_{uuid.uuid4().hex[:8]}"
    raw_data["trip_id"] = trip_id
    raw_data["destination"] = destination
    raw_data.setdefault("source_notes", [])

    # 5. Pydantic 校验
    itinerary = Itinerary.model_validate(raw_data)

    # 6. 记录 token 消耗
    token_usage = TokenUsage(
        planner_prompt_tokens=token_info.get("prompt_tokens", 0),
        planner_completion_tokens=token_info.get("completion_tokens", 0),
    )
    itinerary.token_usage = token_usage

    print(f"[Agent] 行程生成完成，共 {len(itinerary.days)} 天，消耗 {token_usage.total_tokens} tokens")
    return itinerary, token_usage

# 导入 LLM_MODEL 用于日志（放在文件底部避免循环导入）
from app.config import LLM_MODEL