"""
llm_client.py — LLM 客户端封装（基于 LangChain ChatOpenAI）

职责：
1. 封装 DashScope（通义千问）的 LLM 调用
2. 统一记录每次调用的 token 消耗
3. 提供全局单例，避免重复创建连接

为什么用 LangChain 的 ChatOpenAI？
→ DashScope 提供 OpenAI 兼容接口，ChatOpenAI 可以直接用，
  无需额外 SDK。LangChain 还提供了 prompt 模板、输出解析器等工具。
"""
from __future__ import annotations

from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)

class LLMClient:
    """
    LLM 客户端，封装 ChatOpenAI。

    每次调用后可以从 response.metadata 里拿到 token 使用量。
    """

    def __init__(self):
        if not LLM_API_KEY:
            raise ValueError("缺少 LLM_API_KEY，请在 .env 中配置")

        # ChatOpenAI 是 LangChain 封装的 OpenAI 兼容客户端
        # DashScope 的 base_url 和 OpenAI 不同，但接口格式一样
        self.llm = ChatOpenAI(
            model=LLM_MODEL,
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
            # temperature: 0 = 最确定（适合生成结构化数据）
            #              1 = 最随机（适合创意写作）
            # 行程规划需要确定性，用 0.3
            temperature=0.3,
        )

    def invoke(self, messages: list) -> tuple[str, dict]:
        """
        调用 LLM 生成回复。

        参数：
            messages: LangChain 消息列表，格式为
                [SystemMessage(content="..."), HumanMessage(content="...")]

        返回：
            (content, token_info)
            - content: LLM 生成的文本（通常是 JSON 字符串）
            - token_info: token 使用量字典，如
              {"prompt_tokens": 500, "completion_tokens": 800, "total_tokens": 1300}
        """
        response = self.llm.invoke(messages)

        # 提取 token 使用量
        # LangChain 的 response.metadata 里有 token_usage（OpenAI 兼容格式）
        token_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            token_info = {
                "prompt_tokens": response.usage_metadata.get("input_tokens", 0),
                "completion_tokens": response.usage_metadata.get("output_tokens", 0),
                "total_tokens": response.usage_metadata.get("total_tokens", 0),
            }
        elif hasattr(response, "response_metadata") and response.response_metadata:
            meta = response.response_metadata
            token_usage = meta.get("token_usage", {})
            token_info = {
                "prompt_tokens": token_usage.get("prompt_tokens", 0),
                "completion_tokens": token_usage.get("completion_tokens", 0),
                "total_tokens": token_usage.get("total_tokens", 0),
            }

        return response.content, token_info

# 全局单例
_llm_client: Optional[LLMClient] = None

def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端单例。"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client