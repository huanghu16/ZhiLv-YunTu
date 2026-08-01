"""
weather_service.py — 高德天气服务（阶段12）

职责：查询指定城市的未来天气预报。

流程：
    城市名 → 地理编码拿 adcode → 天气 API 查预报 → 返回结构化数据

带 Redis 缓存，TTL=30分钟（天气不需要实时刷新）。
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import (
    AMAP_API_KEY,
    AMAP_BASE_URL,
    AMAP_TIMEOUT_SECONDS,
    REDIS_WEATHER_TTL_SECONDS,
)
from app.services.cache_service import get_cached_json, set_cached_json
from app.services.map_service import geocode_address

logger = logging.getLogger(__name__)

def get_weather_forecast(city: str) -> dict[str, Any]:
    """
    获取指定城市的未来天气预报。

    参数：
        city: 城市名，如 "大理"

    返回：
        {city, province, adcode, report_time, days: [{date, day_weather, ...}]}
    """
    # 1. 查缓存
    cache_key = f"weather:forecast:{city.strip().lower()}"
    cached = get_cached_json(cache_key)
    if cached is not None:
        logger.info("weather cache hit: city=%s", city)
        return cached

    # 2. 先地理编码拿到 adcode（高德天气 API 用 adcode 查更准）
    geocode = geocode_address(city, city=city)
    city_code = geocode.get("adcode") if geocode else city

    # 3. 调用高德天气 API
    if not AMAP_API_KEY:
        raise RuntimeError("未配置 AMAP_API_KEY，无法查询天气。")

    params = {
        "key": AMAP_API_KEY,
        "city": city_code or city,
        "extensions": "all",  # all = 返回未来几天预报
    }

    with httpx.Client(timeout=AMAP_TIMEOUT_SECONDS) as client:
        response = client.get(f"{AMAP_BASE_URL}/weather/weatherInfo", params=params)
        response.raise_for_status()
        payload = response.json()

    if payload.get("status") != "1":
        raise RuntimeError(f"高德天气接口调用失败：{payload.get('info', '未知错误')}")

    forecasts = payload.get("forecasts", [])
    if not forecasts:
        raise RuntimeError("未获取到天气预报结果。")

    first = forecasts[0]
    casts = first.get("casts", [])

    days = [
        {
            "date": cast.get("date"),
            "week": cast.get("week"),
            "day_weather": cast.get("dayweather"),
            "night_weather": cast.get("nightweather"),
            "day_temp": cast.get("daytemp"),
            "night_temp": cast.get("nighttemp"),
            "day_wind": cast.get("daywind"),
            "night_wind": cast.get("nightwind"),
        }
        for cast in casts
    ]

    result = {
        "city": first.get("city") or city,
        "province": first.get("province"),
        "adcode": first.get("adcode"),
        "report_time": first.get("reporttime"),
        "days": days,
    }

    set_cached_json(cache_key, result, expire_seconds=REDIS_WEATHER_TTL_SECONDS)
    logger.info("weather cache miss: city=%s, 已写入缓存", city)
    return result