"""
ingest_data.py — 知识库入库脚本

用法：
    cd backend
    python -m scripts.ingest_data

作用：
    读取 data/*.md → 切块 → 向量化 → 存入 ChromaDB。
    这是 RAG 的"离线准备"步骤，只需运行一次（或文档更新后重跑）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保能 import app 包（脚本在 backend/scripts/ 下，需要把 backend 加入 path）
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.rag.document_loader import load_all_guides
from app.rag.vector_db import get_vector_db

def main():
    print("=" * 60)
    print("智旅云图 - 知识库入库脚本")
    print("=" * 60)

    # 1. 加载并切块
    print("\n[1/3] 加载 Markdown 攻略并切块...")
    chunks = load_all_guides()
    print(f"  共 {len(chunks)} 个切块")

    # 2. 初始化向量库
    print("\n[2/3] 初始化向量库...")
    db = get_vector_db()
    existing = db.count()
    print(f"  当前向量库已有 {existing} 条记录")

    # 如果已有数据，先清空再重新入库（保证幂等）
    if existing > 0:
        print("  检测到已有数据，清空后重新入库...")
        db.reset()

    # 3. 向量化并入库
    print("\n[3/3] 向量化并入库（会调用 Embedding API，请稍候）...")
    count = db.upsert_chunks(chunks)
    print(f"  成功入库 {count} 条记录")

    # 4. 验证
    print("\n=== 入库完成 ===")
    print(f"向量库总记录数: {db.count()}")

    # 简单检索测试
    print("\n=== 检索测试 ===")
    test_query = "大理哪里看日落最好"
    print(f"查询: {test_query}")
    results = db.query_by_text(test_query, n_results=3)
    for i, r in enumerate(results, 1):
        print(f"  {i}. [score={r['score']}] {r['metadata'].get('heading', '')}")
        print(f"     {r['content'][:80]}...")

if __name__ == "__main__":
    main()