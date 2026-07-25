"""
retriever.py — RAG 检索器（整合改写 + 检索 + 重排序）

职责：把 Query Rewrite → 向量检索 → Rerank 三个步骤串成完整流程。

这是 RAG 在线阶段的总入口。上层（Agent / Service）只需调用：
    results = retrieve("不想太赶，想看日落", destination="大理")
就能拿到重排序后的高质量检索结果。

流程（阶段9新增缓存环节）：
    用户输入
      → 查缓存（命中则直接返回）
      → Query Rewrite（规则改写）
      → 向量检索（ChromaDB Top10）
      → Rerank（规则重排序 Top3）
      → 写入缓存
      → 返回结果
"""
from __future__ import annotations

import hashlib

from app.config import REDIS_RAG_TTL_SECONDS
from app.rag.query_rewriter import rewrite_query
from app.rag.reranker import rerank
from app.rag.vector_db import get_vector_db
from app.services.cache_service import get_cached_json, set_cached_json

def _build_cache_key(destination: str, query: str) -> str:
    """
    生成 RAG 缓存 key。

    用 hash 而不是原文：避免特殊字符影响 Redis key，也缩短 key 长度。
    """
    query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()[:16]
    return f"rag:{destination}:{query_hash}"

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
    # ── 0. 查缓存（阶段9新增）──────────────────────────
    # 相同查询第二次直接返回缓存，跳过 Embedding 和向量检索
    # Redis 不可用时 get_cached_json 返回 None，自动降级为正常检索
    cache_key = _build_cache_key(destination, user_input)
    cached = get_cached_json(cache_key)
    if cached is not None:
        print(f"[RAG] 缓存命中: {cache_key}")
        return cached

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

    # ── 4. 写入缓存（阶段9新增）──────────────────────
    # TTL=6小时，攻略内容不会频繁变化
    # Redis 不可用时 set_cached_json 直接跳过，不影响返回结果
    set_cached_json(cache_key, results, expire_seconds=REDIS_RAG_TTL_SECONDS)
    print(f"[RAG] 缓存已写入: {cache_key} (TTL={REDIS_RAG_TTL_SECONDS}s)")

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