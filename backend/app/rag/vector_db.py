"""
vector_db.py — 向量库封装（基于 ChromaDB）

职责：
1. 初始化 ChromaDB（持久化到磁盘）
2. 把文档切块 + 向量 + 元数据存入（upsert）
3. 根据查询向量检索最相似的文档切块

ChromaDB 是什么？
→ 轻量级本地向量数据库。数据存在 db/chroma_db 目录，无需单独部署服务。
  它内部用 HNSW 算法建索引，检索速度毫秒级。

核心 API：
- client = chromadb.PersistentClient(path=...)   建立持久化连接
- collection = client.get_or_create_collection(...)  获取/创建集合
- collection.upsert(ids, embeddings, documents, metadatas)  存入数据
- collection.query(query_embeddings, n_results)   按向量检索
"""
from __future__ import annotations

from typing import Optional

import chromadb

from app.config import CHROMA_COLLECTION_NAME, CHROMA_DB_DIR
from app.rag.embedding import get_embedding_client
from app.rag.document_loader import DocumentChunk

class VectorDB:
    """ChromaDB 向量库封装。"""

    def __init__(self):
        # PersistentClient：数据持久化到磁盘，程序重启不丢失
        self.client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        # collection 类似关系数据库的"表"，一个集合存一类文档
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            # cosine：余弦相似度，衡量向量方向是否一致
            # 适合文本语义搜索（不关心向量长度，只关心方向）
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(self, chunks: list[DocumentChunk]) -> int:
        """
        把文档切块存入向量库。

        upsert = update + insert：id 已存在则更新，不存在则插入。
        存入内容：id + 向量 + 原文 + 元数据
        """
        if not chunks:
            return 0

        # 1. 提取每块的文本，批量生成向量
        texts = [chunk.content for chunk in chunks]
        embeddings = get_embedding_client().embed_batch(texts)

        # 2. 准备 ChromaDB 需要的四要素
        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]

        # 3. upsert 到向量库
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        return len(chunks)

    def query_by_text(self, query_text: str, n_results: int = 5) -> tuple[list[dict], dict]:
        """
        用文本查询：先把查询文本向量化，再检索。

        返回：
            (results, embedding_token_info)
            - results: 检索结果列表
            - embedding_token_info: 本次查询 embedding 的 token 消耗
        """
        # 1. 查询文本向量化（用 embed_query 拿到 token 信息）
        query_embedding, embedding_tokens = get_embedding_client().embed_query(query_text)

        # 2. 调用 ChromaDB 检索
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        # 3. 整理成易用的列表格式
        retrieved = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                distance = results["distances"][0][i]
                score = 1.0 - distance
                retrieved.append(
                    {
                        "id": results["ids"][0][i],
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "score": round(score, 4),
                    }
                )
        return retrieved, embedding_tokens

    def count(self) -> int:
        """返回向量库中当前文档数量。"""
        return self.collection.count()

    def reset(self):
        """清空集合（重新入库前调用）。"""
        self.client.delete_collection(CHROMA_COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

# 全局单例
_vector_db: Optional[VectorDB] = None

def get_vector_db() -> VectorDB:
    """获取全局向量库单例。"""
    global _vector_db
    if _vector_db is None:
        _vector_db = VectorDB()
    return _vector_db