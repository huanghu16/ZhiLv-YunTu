"""
retriever.py — RAG 检索器（整合改写 + 检索 + 重排序）

职责：把 Query Rewrite → 向量检索 → Rerank 三个步骤串成完整流程。

这是 RAG 在线阶段的总入口。上层（Agent / Service）只需调用：
    results = retrieve("不想太赶，想看日落", destination="大理")
就能拿到重排序后的高质量检索结果。

流程：
    用户输入
      → Query Rewrite（规则改写）
      → 向量检索（ChromaDB Top10）
      → Rerank（规则重排序 Top3）
      → 返回结果
"""
from __future__ import annotations

from app.rag.query_rewriter import rewrite_query
from app.rag.reranker import rerank
from app.rag.vector_db import get_vector_db

def retrieve(
    user_input: str,
    destination: str = "",
    top_k: int = 3,
    recall_n: int = 10,
) -> list[dict]:
    """
    完整的 RAG 在线检索流程。

    参数：
        user_input: 用户的原始输入，如 "不想太赶，想看日落"
        destination: 目的地（中文），如 "大理"
        top_k: 最终返回几个结果
        recall_n: 向量检索阶段召回几个候选（要多召回，再由 rerank 筛选）

    返回：
        重排序后的检索结果列表，每个元素含：
        - content: 攻略正文
        - metadata: 元数据（city/heading/section）
        - score: 原始向量相似度
        - rerank_score: 重排序后的分数
        - rewritten_query: 改写后的查询（用于调试）
    """
    # ── 1. Query Rewrite ──────────────────────────────
    rewritten = rewrite_query(user_input, destination)

    # ── 2. 向量检索（多召回）──────────────────────────
    # recall_n 设为 10：先粗筛 10 个候选，再精排 top_k 个
    # 这就是"召回"和"排序"分离的经典设计
    db = get_vector_db()
    candidates = db.query_by_text(rewritten, n_results=recall_n)

    # ── 3. Rerank（精排）──────────────────────────────
    results = rerank(candidates, rewritten, destination, top_k=top_k)

    # 给每个结果附上改写后的查询（方便调试）
    for r in results:
        r["rewritten_query"] = rewritten

    return results

def retrieve_for_planning(
    destination: str,
    preferences: list[str] | None = None,
    special_notes: str | None = None,
    top_k: int = 3,
) -> list[dict]:
    """
    专为行程规划设计的检索入口。

    把目的地的偏好和特殊要求组合成查询，检索相关攻略。
    上层 trip_service.py 会调用这个函数。

    参数：
        destination: 目的地（中文），如 "大理"
        preferences: 偏好标签列表，如 ["自然风景", "美食"]
        special_notes: 特殊要求，如 "想看日落"
        top_k: 返回几个结果
    """
    # 组合查询：目的地 + 偏好 + 特殊要求
    parts = [destination]
    if preferences:
        parts.extend(preferences)
    if special_notes:
        parts.append(special_notes)
    query = " ".join(parts)

    return retrieve(query, destination=destination, top_k=top_k)