"""
reranker.py — 重排序（阶段10：LLM + 规则降级）

职责：对向量检索返回的候选片段，重新打分排序，选出最相关的。

阶段10更新：
    新增 DashScope rerank 模型（Cross-encoder）重排序。
    rerank 模型专门训练来给"查询-文档"对打相关性分，比规则更精准。
    LLM 调用失败时自动降级到规则版（关键词命中打分）。

    什么是 Cross-encoder？
    → 普通向量检索把查询和文档分别编码成向量再算距离（Bi-encoder）。
      Cross-encoder 把查询和文档拼在一起送入模型，能捕捉更细的语义关系。
      精度更高但速度慢，所以只用于少量候选的精排。
"""
from __future__ import annotations

from app.config import LLM_API_KEY, RERANK_MODEL, USE_LLM_RERANK

# ═══════════════════════════════════════════════════════════
# 规则版重排序（原有代码，作为降级方案）
# ═══════════════════════════════════════════════════════════

def _rerank_by_rules(
    candidates: list[dict],
    query: str,
    destination: str = "",
    top_k: int = 3,
) -> list[dict]:
    """
    规则重排序（降级方案）。

    打分维度：
    1. 关键词命中：查询词出现在正文里 → 加分
    2. 标题命中：查询词出现在标题里 → 大幅加分
    3. 城市匹配：查询的城市和文档的城市一致 → 加分
    4. 向量相似度：保留原始 embedding 分数作为基础分
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

# ═══════════════════════════════════════════════════════════
# LLM 版重排序（阶段10新增）
# ═══════════════════════════════════════════════════════════

def _rerank_by_llm(
    candidates: list[dict],
    query: str,
    destination: str = "",
    top_k: int = 3,
) -> list[dict]:
    """
    用 DashScope rerank 模型重排序（Cross-encoder）。

    调用 DashScope 的 text-rerank 接口，让模型给每个候选打相关性分。

    为什么用 httpx 直接调？
    → DashScope 的 rerank 接口不是 OpenAI 兼容格式，
      LangChain 没有封装，所以用 httpx 直接发 HTTP 请求。
    """
    import httpx

    if not candidates:
        return []

    # 准备请求参数
    # 把每个候选的 content 提取出来作为 documents
    documents = [c.get("content", "") for c in candidates]

    # DashScope rerank API 地址
    url = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": top_k,
        "return_documents": False,  # 只要分数和索引，不要返回原文
    }

    # 调用 API（超时 10 秒）
    with httpx.Client(timeout=10.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    # 解析返回结果
    # 返回格式：{"output": {"results": [{"index": 0, "relevance_score": 0.95}, ...]}}
    results = data.get("output", {}).get("results", [])

    if not results:
        raise ValueError("Rerank API 返回空结果")

    # 按 rerank 模型返回的顺序重新组织候选列表
    reranked: list[dict] = []
    for r in results:
        idx = r["index"]
        score = r["relevance_score"]
        candidate = candidates[idx].copy()
        candidate["rerank_score"] = round(score, 4)
        candidate["rerank_detail"] = {
            "method": "llm_cross_encoder",
            "model": RERANK_MODEL,
            "base_score": candidate.get("score", 0.0),
        }
        reranked.append(candidate)

    print(f"[Rerank] LLM 重排序完成，{len(reranked)} 个结果，"
          f"最高分: {reranked[0]['rerank_score'] if reranked else 'N/A'}")

    return reranked[:top_k]

# ═══════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════

def rerank(
    candidates: list[dict],
    query: str,
    destination: str = "",
    top_k: int = 3,
) -> list[dict]:
    """
    对检索候选结果进行重排序。

    优先使用 LLM rerank 模型，失败时降级到规则版。

    参数：
        candidates: 向量检索返回的候选列表，每个元素含 content/metadata/score
        query: 改写后的查询字符串，如 "大理 日落 景点"
        destination: 目的地（中文），如 "大理"
        top_k: 返回前几个结果

    返回：
        重排序后的 top_k 个结果，每个增加 rerank_score 字段
    """
    # 开关关闭 → 直接用规则版
    if not USE_LLM_RERANK:
        return _rerank_by_rules(candidates, query, destination, top_k)

    # 开关开启 → 尝试 LLM，失败降级
    try:
        return _rerank_by_llm(candidates, query, destination, top_k)
    except Exception as e:
        print(f"[Rerank] LLM 重排序失败，降级到规则版: {e}")
        return _rerank_by_rules(candidates, query, destination, top_k)