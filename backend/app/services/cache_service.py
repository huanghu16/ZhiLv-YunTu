"""
cache_service.py — 缓存服务（阶段9）

职责：
    提供统一的 Redis 缓存读写接口，对上层屏蔽 Redis 是否可用的细节。

核心设计：优雅降级
    Redis 不可用时（未安装、未启动、连接失败），缓存函数直接跳过，
    主业务流程照常执行。缓存是优化，不是必需——没有缓存系统也能跑。

核心函数：
    - get_cached_json(key) -> Any | None   读缓存
    - set_cached_json(key, value, ttl)     写缓存
    - delete_cached(key)                   删缓存
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import (
    REDIS_DEFAULT_TTL_SECONDS,
    REDIS_ENABLED,
    REDIS_KEY_PREFIX,
    REDIS_URL,
)

# 尝试导入 redis，未安装时设为 None（优雅降级）
try:
    import redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)

# 全局 Redis 客户端单例（懒加载，第一次调用时才创建）
_redis_client: Any | None = None
# 标记是否已记录过降级警告，避免日志刷屏
_degradation_logged = False

def _build_key(key: str) -> str:
    """为缓存 key 添加统一前缀，避免不同项目之间冲突。"""
    return f"{REDIS_KEY_PREFIX}:{key}"

def _get_redis_client():
    """
    获取 Redis 客户端（懒加载单例）。

    返回 None 的三种情况（都会触发优雅降级）：
    1. REDIS_ENABLED=false（配置关闭）
    2. redis 包未安装
    3. Redis 服务连接失败
    """
    global _redis_client
    global _degradation_logged

    # 情况1：配置关闭
    if not REDIS_ENABLED:
        return None

    # 情况2：依赖未安装
    if redis is None:
        if not _degradation_logged:
            logger.warning("Redis 已启用，但未安装 redis 依赖，缓存功能将被跳过")
            _degradation_logged = True
        return None

    # 已有客户端，直接复用
    if _redis_client is not None:
        return _redis_client

    # 第一次：创建客户端并测试连接
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()  # 测试连接是否通畅
        _redis_client = client
        logger.info("Redis 连接成功: %s", REDIS_URL)
        return _redis_client
    except Exception as exc:
        # 情况3：连接失败
        if not _degradation_logged:
            logger.warning("Redis 连接失败，缓存功能将被跳过: %s", exc)
            _degradation_logged = True
        return None

def get_cached_json(key: str) -> Any | None:
    """
    读取 JSON 缓存。

    返回：
        缓存的 Python 对象，未命中或 Redis 不可用时返回 None
    """
    client = _get_redis_client()
    if client is None:
        return None

    try:
        raw_value = client.get(_build_key(key))
        if raw_value is None:
            return None
        return json.loads(raw_value)
    except Exception as exc:
        # 缓存读取失败不影响主流程
        logger.debug("读取缓存失败 [%s]: %s", key, exc)
        return None

def set_cached_json(
    key: str,
    value: Any,
    expire_seconds: int | None = None,
) -> None:
    """写入 JSON 缓存。Redis 不可用时直接跳过。"""
    client = _get_redis_client()
    if client is None:
        return

    ttl = expire_seconds or REDIS_DEFAULT_TTL_SECONDS
    try:
        client.set(
            _build_key(key),
            json.dumps(value, ensure_ascii=False),
            ex=ttl,
        )
    except Exception as exc:
        logger.debug("写入缓存失败 [%s]: %s", key, exc)

def delete_cached(key: str) -> None:
    """删除缓存。"""
    client = _get_redis_client()
    if client is None:
        return

    try:
        client.delete(_build_key(key))
    except Exception as exc:
        logger.debug("删除缓存失败 [%s]: %s", key, exc)

def is_cache_available() -> bool:
    """检查缓存是否可用（用于调试和状态展示）。"""
    return _get_redis_client() is not None