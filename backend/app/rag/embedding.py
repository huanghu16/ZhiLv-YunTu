"""
embedding.py — 文本向量化封装

职责：把文本（字符串）变成向量（浮点数组）。

原理：
- DashScope 提供 text-embedding-v4 模型
- 输入一段文本，输出 1024 维浮点数组
- 语义相近的文本，向量距离也近（余弦相似度高）

为什么单独封装一个模块？
→ 向量库、检索器、Rerank 等多处都要用 embedding。
  封装一处，统一调用，方便维护和换模型。
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from app.config import EMBEDDING_MODEL, LLM_API_KEY, LLM_BASE_URL

class EmbeddingClient:
    """
    文本向量化客户端，封装 DashScope Embedding API。

    DashScope 的 Embedding 接口路径：
        POST {base_url}/embeddings
    请求体：
        {"model": "text-embedding-v4", "input": ["文本1", "文本2"]}
    响应体：
        {"data": [{"embedding": [0.1, 0.2, ...], "index": 0}, ...]}
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or LLM_API_KEY
        self.base_url = base_url or LLM_BASE_URL
        self.model = model or EMBEDDING_MODEL

        if not self.api_key:
            raise ValueError("缺少 LLM_API_KEY，请在 .env 中配置")

    def embed(self, text: str) -> list[float]:
        """把单段文本变成向量。"""
        vectors = self.embed_batch([text])
        return vectors[0]

    def embed_query(self, text: str) -> tuple[list[float], dict]:
        """
        单条文本向量化（在线检索专用），同时返回 token 使用量。

        和 embed() 的区别：
        - embed() 只返回向量，给离线入库用
        - embed_query() 返回 (向量, token信息)，给在线检索用

        为什么分开？
        → 离线入库不需要统计 token，在线检索需要。
        """
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": [text],
            "dimensions": 1024,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        result = response.json()

        # 提取向量
        embeddings_data = sorted(result["data"], key=lambda x: x["index"])
        vector = embeddings_data[0]["embedding"]

        # 提取 token 使用量
        # DashScope embedding 返回格式：{"usage": {"prompt_tokens": 20, "total_tokens": 20}}
        # embedding 没有 completion_tokens（输出是向量不是文本），所以为 0
        usage = result.get("usage", {})
        token_info = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": 0,
        }

        print(f"[embedding] query embedding token: "
              f"prompt={token_info['prompt_tokens']}, "
              f"completion=0, source=api")

        return vector, token_info

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批量向量化，减少 API 调用次数。

        DashScope text-embedding-v4 单次最多 25 条文本。
        这里按 EMBEDDING_BATCH_SIZE 分批处理。
        """
        from app.config import EMBEDDING_BATCH_SIZE

        all_vectors: list[list[float]] = []
        # 按 batch_size 分批
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            batch_vectors = self._call_embedding_api(batch)
            all_vectors.extend(batch_vectors)
        return all_vectors

    def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
        """实际调用 DashScope Embedding API。"""
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
            # text-embedding-v4 支持指定维度，默认 1024
            "dimensions": 1024,
        }

        # httpx 是 Python 的 HTTP 客户端，比 requests 更现代
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()  # 如果状态码不是 2xx，抛异常

        result = response.json()
        # 响应格式：{"data": [{"embedding": [...], "index": 0}, ...]}
        # 按 index 排序，保证顺序和输入一致
        embeddings_data = sorted(result["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in embeddings_data]

# 全局单例，整个项目共用一个 embedding 客户端
_embedding_client: Optional[EmbeddingClient] = None

def get_embedding_client() -> EmbeddingClient:
    """获取全局 embedding 客户端单例。第一次调用时创建。"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client