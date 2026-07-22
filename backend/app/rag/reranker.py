"""
reranker.py — 重排序（规则版）

职责：对向量检索返回的候选片段，用规则重新打分排序，选出最相关的。

为什么需要重排序？
→ 向量检索（Embedding 相似度）是"语义粗筛"，速度快但不够精准。
  比如查"大理日落"，检索可能返回 10 个结果，其中第 5 个才是
  真正讲洱海日落的，但它的向量相似度分数不如第 1 个讲大理古城的。
  Rerank 用更细致的规则重新打分，把真正相关的排到前面。

本阶段用规则实现，打分维度：
1. 关键词命中：查询词出现在正文里 → 加分
2. 标题命中：查询词出现在标题里 → 大幅加分（标题是主题摘要）
3. 城市匹配：查询的城市和文档的城市一致 → 加分
4. 向量相似度：保留原始 embedding 分数作为基础分
"""
from __future__ import annotations

def rerank(
    candidates: list[dict],
    query: str,
    destination: str = "",
    top_k: int = 3,
) -> list[dict]:
    """
    对检索候选结果进行规则重排序。

    参数：
        candidates: 向量检索返回的候选列表，每个元素含 content/metadata/score
        query: 改写后的查询字符串，如 "大理 日落 景点"
        destination: 目的地（中文），如 "大理"
        top_k: 返回前几个结果

    返回：
        重排序后的 top_k 个结果，每个增加 rerank_score 字段
    """
    if not candidates:
        return []

    query_words = set(query.split())

    # 目的地的英文 key（用于匹配 metadata 里的 city 字段）
    from app.rag.query_rewriter import CITY_ALIASES
    dest_key = CITY_ALIASES.get(destination, "")

    scored: list[dict] = []
    for candidate in candidates:
        content = candidate.get("content", "")
        metadata = candidate.get("metadata", {})
        heading = metadata.get("heading", "")
        city = metadata.get("city", "")
        base_score = candidate.get("score", 0.0)  # 原始向量相似度分

        # ── 打分维度 ──────────────────────────────────

        # 1. 基础分：向量相似度（0-1），权重 50%
        final_score = base_score * 0.5

        # 2. 关键词命中（正文）：每个命中词加 0.05
        content_hits = 0
        for word in query_words:
            if word and word in content:
                content_hits += 1
        final_score += min(content_hits * 0.05, 0.15)  # 上限 0.15

        # 3. 标题命中：每个命中词加 0.1（标题权重更高）
        heading_hits = 0
        for word in query_words:
            if word and word in heading:
                heading_hits += 1
        final_score += min(heading_hits * 0.1, 0.2)  # 上限 0.2

        # 4. 城市匹配：目的地和文档城市一致，加 0.1
        if dest_key and city == dest_key:
            final_score += 0.1

        # 复制候选结果，加上 rerank_score
        reranked = candidate.copy()
        reranked["rerank_score"] = round(final_score, 4)
        reranked["rerank_detail"] = {
            "base_score": round(base_score, 4),
            "content_hits": content_hits,
            "heading_hits": heading_hits,
            "city_match": dest_key == city if dest_key else False,
        }
        scored.append(reranked)

    # 按 rerank_score 降序排序
    scored.sort(key=lambda x: x["rerank_score"], reverse=True)

    return scored[:top_k]