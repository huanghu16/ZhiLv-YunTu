"""
verify_stage3.py — 阶段 3 验证脚本

用法：
    cd backend
    python -m scripts.verify_stage3

对比"不优化"和"优化后"的检索效果差异。
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.rag.query_rewriter import rewrite_query
from app.rag.vector_db import get_vector_db
from app.rag.retriever import retrieve

def main():
    print("=" * 60)
    print("阶段 3 验证：Query Rewrite + Rerank 效果对比")
    print("=" * 60)

    # 测试用例
    test_cases = [
        {
            "input": "不想太赶，想看日落",
            "destination": "大理",
            "desc": "口语化 + 意图隐含",
        },
        {
            "input": "带爸妈去，想轻松一点",
            "destination": "丽江",
            "desc": "人群 + 节奏偏好",
        },
        {
            "input": "想吃当地特色美食",
            "destination": "成都",
            "desc": "美食意图",
        },
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n{'─' * 60}")
        print(f"测试 {i}: {case['desc']}")
        print(f"原始输入: {case['input']}")
        print(f"目的地: {case['destination']}")

        # ── 对比 A：不优化（直接检索）──────────────────
        print(f"\n  [A] 不优化（直接检索）:")
        db = get_vector_db()
        raw_query = f"{case['destination']} {case['input']}"
        results_a = db.query_by_text(raw_query, n_results=3)
        for j, r in enumerate(results_a, 1):
            heading = r["metadata"].get("heading", "")
            print(f"    {j}. [score={r['score']}] {heading}")
            print(f"       {r['content'][:60].replace(chr(10), ' ')}...")

        # ── 对比 B：优化后（Rewrite + Rerank）──────────
        print(f"\n  [B] 优化后（Rewrite + Rerank）:")
        rewritten = rewrite_query(case["input"], case["destination"])
        print(f"    改写后查询: {rewritten}")
        results_b = retrieve(case["input"], destination=case["destination"], top_k=3)
        for j, r in enumerate(results_b, 1):
            heading = r["metadata"].get("heading", "")
            rerank_score = r["rerank_score"]
            detail = r["rerank_detail"]
            print(f"    {j}. [rerank={rerank_score}] {heading}")
            print(f"       base={detail['base_score']} hits={detail['content_hits']}+{detail['heading_hits']} city={detail['city_match']}")
            print(f"       {r['content'][:60].replace(chr(10), ' ')}...")

    print(f"\n{'─' * 60}")
    print("验证完成。对比 A 和 B 的结果，B 应该更精准命中意图。")

if __name__ == "__main__":
    main()