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
) -> tuple[list[dict], dict]:
    """
    完整的 RAG 在线检索流程。

    返回：
        (results, token_info)
        - results: 重排序后的检索结果列表
        - token_info: 包含 rewrite/embedding/rerank 三段 token 的字典
    """
    # token 信息初始化（缓存命中时返回全 0）
    token_info = {
        "rewrite": {"prompt_tokens": 0, "completion_tokens": 0},
        "embedding": {"prompt_tokens": 0, "completion_tokens": 0},
        "rerank": {"prompt_tokens": 0, "completion_tokens": 0},
    }

    # ── 0. 查缓存 ──────────────────────────────────────
    cache_key = _build_cache_key(destination, user_input)
    cached = get_cached_json(cache_key)
    if cached is not None:
        print(f"[RAG] 缓存命中: {cache_key}")
        return cached, token_info  # 缓存命中，token 全 0

    # ── 1. Query Rewrite ──────────────────────────────
    rewritten, rewrite_tokens = rewrite_query(user_input, destination)
    token_info["rewrite"] = rewrite_tokens

    # ── 2. 向量检索（多召回）──────────────────────────
    db = get_vector_db()
    candidates, embedding_tokens = db.query_by_text(rewritten, n_results=recall_n)
    token_info["embedding"] = embedding_tokens

    # ── 3. Rerank（精排）──────────────────────────────
    results, rerank_tokens = rerank(candidates, rewritten, destination, top_k=top_k)
    token_info["rerank"] = rerank_tokens

    # 给每个结果附上改写后的查询（方便调试）
    for r in results:
        r["rewritten_query"] = rewritten

    # ── 4. 写入缓存 ──────────────────────────────────
    set_cached_json(cache_key, results, expire_seconds=REDIS_RAG_TTL_SECONDS)
    print(f"[RAG] 缓存已写入: {cache_key} (TTL={REDIS_RAG_TTL_SECONDS}s)")

    return results, token_info

def retrieve_for_planning(
    destination: str,
    preferences: list[str] | None = None,
    special_notes: str | None = None,
    top_k: int = 3,
) -> tuple[list[dict], dict]:
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