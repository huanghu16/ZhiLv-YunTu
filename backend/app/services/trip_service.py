"""
trip_service.py — 行程主编排服务

职责：
    把 RAG 检索、LLM 生成、地图补全、天气补充等步骤，
    按固定顺序串联起来，完成"一次完整的行程规划"。

这是整个项目的"指挥中心"。上层（API 路由层）只需调用：
    itinerary = await trip_service.plan_trip(trip_request)
就能拿到完整行程。

什么是"显式编排"（Workflow）？
→ 步骤的执行顺序是写死在代码里的（固定 5 步），
  不是由 LLM 自己决定下一步做什么。
  适合"业务流程确定"的场景。真正的自主 Agent 会
  自己决定调用哪个工具、什么顺序，本项目不是那种。
"""
from __future__ import annotations

from app.agents.trip_planner_agent import generate_itinerary
from app.config import ENABLE_AMAP_ENRICHMENT
from app.models.schemas import Itinerary, TripRequest, TokenUsage
from app.rag.retriever import retrieve_for_planning

def _format_rag_context(results: list[dict]) -> str:
    """
    把 RAG 检索结果格式化成给 LLM 的参考文本。

    输入：[{content, metadata, score, rerank_score}, ...]
    输出：一段拼接好的攻略文本，每段带标题
    """
    if not results:
        return "暂无攻略参考信息。"

    parts = []
    for r in results:
        heading = r.get("metadata", {}).get("heading", "未知")
        section = r.get("metadata", {}).get("section", "")
        content = r.get("content", "")
        title = f"【{section} - {heading}】" if section else f"【{heading}】"
        parts.append(f"{title}\n{content}")

    return "\n\n".join(parts)

def _build_source_notes(results: list[dict]) -> list[str]:
    """
    从 RAG 检索结果生成"来源说明"，附在行程末尾。

    让用户知道行程参考了哪些攻略片段（可追溯）。
    """
    notes = []
    for r in results:
        heading = r.get("metadata", {}).get("heading", "")
        source = r.get("metadata", {}).get("source", "")
        notes.append(f"参考攻略: {source} - {heading}")
    return notes

def plan_trip(request: TripRequest) -> Itinerary:
    """
    行程规划主编排函数（核心入口）。

    执行流程（固定 5 步）：
    1. RAG 检索：根据目的地+偏好检索相关攻略
    2. LLM 生成：把攻略 + 用户需求交给 LLM 生成行程
    3. 地图补全：补充景点经纬度/地址（当前跳过）
    4. 天气补充：补充天气预报（当前跳过）
    5. 附加来源说明 + token 统计

    参数：
        request: TripRequest 对象，含目的地/日期/预算/偏好等

    返回：
        Itinerary 对象（完整行程）
    """
    print(f"\n[Service] 开始规划行程: {request.destination}, "
          f"{request.start_date} ~ {request.end_date}, "
          f"{request.travelers}人, 预算{request.budget}元")

    # ── 步骤 1: RAG 检索攻略 ──────────────────────────
    print("[Service] 步骤1/5: RAG 检索攻略...")
    # 把偏好和特殊要求组合成检索查询
    rag_results = retrieve_for_planning(
        destination=request.destination,
        preferences=request.preferences,
        special_notes=request.special_notes,
        top_k=3,
    )
    rag_context = _format_rag_context(rag_results)
    source_notes = _build_source_notes(rag_results)
    print(f"  检索到 {len(rag_results)} 条攻略")

    # ── 步骤 2: LLM 生成行程 ──────────────────────────
    print("[Service] 步骤2/5: LLM 生成行程...")
    itinerary, token_usage = generate_itinerary(
        destination=request.destination,
        start_date=request.start_date,
        end_date=request.end_date,
        travelers=request.travelers,
        budget=request.budget,
        preferences=request.preferences,
        pace=request.pace,
        dietary_preferences=request.dietary_preferences,
        hotel_level=request.hotel_level,
        special_notes=request.special_notes,
        rag_context=rag_context,
    )

    # ── 步骤 3: 地图补全（当前跳过）──────────────────
    print("[Service] 步骤3/5: 地图补全...")
    if ENABLE_AMAP_ENRICHMENT:
        # 阶段9接入高德地图 API，补充景点经纬度/地址/图片
        # itinerary = enrich_with_map_data(itinerary)
        print("  地图补全已启用（待阶段9实现）")
    else:
        print("  地图补全已关闭（ENABLE_AMAP_ENRICHMENT=false）")

    # ── 步骤 4: 天气补充（当前跳过）──────────────────
    print("[Service] 步骤4/5: 天气补充...")
    # 阶段9接入天气 API
    print("  天气补充待阶段9实现，跳过")

    # ── 步骤 5: 附加来源说明 + token 统计 ────────────
    print("[Service] 步骤5/5: 附加来源说明...")
    itinerary.source_notes = source_notes
    # token_usage 已经在 generate_itinerary 里设好了，这里确认一下
    if itinerary.token_usage is None:
        itinerary.token_usage = token_usage

    print(f"[Service] 行程规划完成!")
    print(f"  行程ID: {itinerary.trip_id}")
    print(f"  天数: {len(itinerary.days)}")
    print(f"  Token消耗: {itinerary.token_usage.total_tokens}")

    return itinerary

def edit_trip(
    trip_id: str,
    current_itinerary: Itinerary,
    user_instruction: str,
    edit_scope: str | None = None,
    preserve_constraints: list[str] | None = None,
) -> Itinerary:
    """
    编辑已有行程（阶段6的 API 会用到）。

    当前版本是简化实现：把用户新要求 + 当前行程交给 LLM 重新生成。
    后续可以做成"局部修改"（只改某一天）。
    """
    from app.agents.llm_client import get_llm_client
    from langchain_core.messages import HumanMessage, SystemMessage

    print(f"\n[Service] 编辑行程: {trip_id}, 要求: {user_instruction}")

    system_prompt = """你是一位旅行规划师。用户想修改已有的行程。
根据用户的修改要求，调整行程后输出完整的 JSON 行程对象。
保持未提及部分不变。输出格式与之前相同，只输出 JSON。"""

    # 把当前行程序列化成文本给 LLM 参考
    import json
    current_json = current_itinerary.model_dump_json(indent=2)

    human_prompt = f"""当前行程：
{current_json}

用户修改要求：{user_instruction}

请根据要求修改行程，输出完整的 JSON。"""

    client = get_llm_client()
    content, token_info = client.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ])

    # 解析新行程
    from app.agents.trip_planner_agent import _extract_json
    raw_data = _extract_json(content)
    raw_data["trip_id"] = trip_id  # 保持原有 ID
    raw_data["destination"] = current_itinerary.destination
    raw_data.setdefault("source_notes", current_itinerary.source_notes)

    new_itinerary = Itinerary.model_validate(raw_data)

    # 合并 token 统计
    edit_tokens = TokenUsage(
        planner_prompt_tokens=token_info.get("prompt_tokens", 0),
        planner_completion_tokens=token_info.get("completion_tokens", 0),
    )
    if current_itinerary.token_usage:
        edit_tokens.planner_prompt_tokens += current_itinerary.token_usage.planner_prompt_tokens
        edit_tokens.planner_completion_tokens += current_itinerary.token_usage.planner_completion_tokens
    new_itinerary.token_usage = edit_tokens

    print(f"[Service] 行程编辑完成, Token消耗: {edit_tokens.total_tokens}")
    return new_itinerary