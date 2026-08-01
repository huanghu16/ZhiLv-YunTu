"""
map_service.py — 高德地图服务（阶段12）

职责：
    1. 地理编码：地址 → 经纬度
    2. POI 搜索：关键词 → 景点信息（地址/经纬度/图片）
    3. 路线估算：两点 → 距离/耗时
    4. 行程补全（enrich）：遍历 itinerary，给每个景点/酒店/交通补全地图数据

每个 API 调用都带 Redis 缓存，减少重复请求。
高德 Key 未配置时，所有操作静默跳过，不影响主流程。
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import (
    AMAP_API_KEY,
    AMAP_BASE_URL,
    AMAP_DEFAULT_CITY,
    AMAP_TIMEOUT_SECONDS,
    ENABLE_AMAP_ENRICHMENT,
    REDIS_MAP_TTL_SECONDS,
)
from app.models.schemas import HotelItem, Itinerary, SpotItem, TransportItem
from app.services.cache_service import get_cached_json, set_cached_json

logger = logging.getLogger(__name__)

def _ensure_amap_api_key() -> None:
    """确保已配置高德 Key，没配置就抛异常。"""
    if not AMAP_API_KEY:
        raise RuntimeError("未配置 AMAP_API_KEY，无法调用高德地图服务。")

def _request_amap(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """调用高德地图 API 并返回 JSON。"""
    _ensure_amap_api_key()

    request_params = {
        "key": AMAP_API_KEY,
        **params,
    }

    with httpx.Client(timeout=AMAP_TIMEOUT_SECONDS) as client:
        response = client.get(f"{AMAP_BASE_URL}{path}", params=request_params)
        response.raise_for_status()
        payload = response.json()

    # 高德返回 status="1" 表示成功
    if payload.get("status") != "1":
        info = payload.get("info", "未知错误")
        raise RuntimeError(f"高德地图接口调用失败：{info}")

    return payload

def _parse_float(value: str | None) -> float | None:
    """字符串安全转浮点数。"""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _split_location(location: str | None) -> tuple[float | None, float | None]:
    """
    高德返回的 location 格式是 "经度,纬度"（注意顺序！）。
    拆成 (纬度, 经度) 返回，和 schemas.py 里的字段对应。
    """
    if not location or "," not in location:
        return None, None
    lon_str, lat_str = location.split(",", 1)
    return _parse_float(lat_str), _parse_float(lon_str)

def _normalize_cache_text(value: str | None) -> str:
    """缓存 key 文本标准化。"""
    if value is None:
        return ""
    return value.strip().lower()

# ═══════════════════════════════════════════════════════════
# 核心功能 1：地理编码
# ═══════════════════════════════════════════════════════════

def geocode_address(address: str, city: str | None = None) -> dict[str, Any] | None:
    """
    地址 → 经纬度（地理编码）。

    参数：
        address: 地址文本，如 "大理古城"
        city: 城市名，如 "大理"（可选，提升精度）

    返回：
        {formatted_address, province, city, district, adcode, latitude, longitude}
        找不到返回 None
    """
    cache_key = f"map:geocode:{_normalize_cache_text(address)}:{_normalize_cache_text(city or AMAP_DEFAULT_CITY)}"
    cached = get_cached_json(cache_key)
    if cached is not None:
        logger.info("map geocode cache hit: address=%s", address)
        return cached

    payload = _request_amap("/geocode/geo", {
        "address": address,
        "city": city or AMAP_DEFAULT_CITY,
    })

    geocodes = payload.get("geocodes", [])
    if not geocodes:
        return None

    first = geocodes[0]
    latitude, longitude = _split_location(first.get("location"))
    result = {
        "formatted_address": first.get("formatted_address", address),
        "province": first.get("province"),
        "city": first.get("city"),
        "district": first.get("district"),
        "adcode": first.get("adcode"),
        "latitude": latitude,
        "longitude": longitude,
    }
    set_cached_json(cache_key, result, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return result

# ═══════════════════════════════════════════════════════════
# 核心功能 2：POI 搜索
# ═══════════════════════════════════════════════════════════

def search_places(
    keyword: str,
    city: str | None = None,
    page_size: int = 5,
) -> list[dict[str, Any]]:
    """
    关键词 → POI 列表（兴趣点搜索）。

    返回的每个 POI 包含：名称、地址、经纬度、POI ID、图片 URL。
    """
    cache_key = f"map:place:{_normalize_cache_text(keyword)}:{_normalize_cache_text(city or AMAP_DEFAULT_CITY)}:{page_size}"
    cached = get_cached_json(cache_key)
    if cached is not None:
        logger.info("map place cache hit: keyword=%s", keyword)
        return cached

    payload = _request_amap("/place/text", {
        "keywords": keyword,
        "city": city or AMAP_DEFAULT_CITY,
        "offset": page_size,
        "page": 1,
        "extensions": "all",  # 返回详细信息（含图片）
    })

    pois = payload.get("pois", [])
    results: list[dict[str, Any]] = []
    for poi in pois:
        latitude, longitude = _split_location(poi.get("location"))
        # 图片可能有多张，取第一张
        photos = poi.get("photos") if isinstance(poi.get("photos"), list) else []
        first_photo = photos[0] if photos and isinstance(photos[0], dict) else {}
        results.append({
            "name": poi.get("name"),
            "address": poi.get("address"),
            "poi_id": poi.get("id"),
            "image_url": first_photo.get("url"),
            "latitude": latitude,
            "longitude": longitude,
        })

    set_cached_json(cache_key, results, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return results

# ═══════════════════════════════════════════════════════════
# 核心功能 3：路线估算
# ═══════════════════════════════════════════════════════════

def estimate_route(
    origin_longitude: float,
    origin_latitude: float,
    destination_longitude: float,
    destination_latitude: float,
) -> dict[str, Any] | None:
    """
    两点 → 驾车距离和耗时估算。
    """
    cache_key = (
        f"map:route:"
        f"{origin_longitude:.6f},{origin_latitude:.6f}:"
        f"{destination_longitude:.6f},{destination_latitude:.6f}"
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        logger.info("map route cache hit")
        return cached

    payload = _request_amap("/direction/driving", {
        "origin": f"{origin_longitude},{origin_latitude}",
        "destination": f"{destination_longitude},{destination_latitude}",
        "strategy": 0,  # 0 = 速度优先
    })

    route = payload.get("route", {})
    paths = route.get("paths", [])
    if not paths:
        return None

    first_path = paths[0]
    distance_meters = _parse_float(first_path.get("distance"))
    duration_seconds = _parse_float(first_path.get("duration"))

    result = {
        "distance_meters": distance_meters,
        "distance_km": round(distance_meters / 1000, 2) if distance_meters else None,
        "duration_seconds": duration_seconds,
        "estimated_minutes": round(duration_seconds / 60) if duration_seconds else None,
    }
    set_cached_json(cache_key, result, expire_seconds=REDIS_MAP_TTL_SECONDS)
    return result

# ═══════════════════════════════════════════════════════════
# 核心功能 4：行程补全（enrich）
# ═══════════════════════════════════════════════════════════

def _pick_best_place(keyword: str, city: str | None = None) -> dict[str, Any] | None:
    """POI 搜索取第一条结果。"""
    results = search_places(keyword=keyword, city=city, page_size=1)
    return results[0] if results else None

def _enrich_spot(spot: SpotItem, city: str | None = None) -> bool:
    """补全单个景点：POI搜索 → 地理编码兜底。"""
    place = _pick_best_place(spot.name, city=city)
    if place is None and spot.location:
        place = _pick_best_place(spot.location, city=city)

    if place is None:
        # POI 搜不到，尝试地理编码
        query_address = spot.address or spot.location or spot.name
        geocode = geocode_address(query_address, city=city)
        if geocode is None:
            return False
        spot.address = geocode.get("formatted_address") or spot.address
        spot.latitude = geocode.get("latitude")
        spot.longitude = geocode.get("longitude")
        return True

    spot.address = place.get("address") or spot.address
    spot.image_url = place.get("image_url") or spot.image_url
    spot.latitude = place.get("latitude")
    spot.longitude = place.get("longitude")
    spot.poi_id = place.get("poi_id") or spot.poi_id
    return True

def _enrich_hotel(hotel: HotelItem, city: str | None = None) -> bool:
    """补全单个酒店。"""
    place = _pick_best_place(hotel.name, city=city)
    if place is None and hotel.location:
        place = _pick_best_place(hotel.location, city=city)

    if place is None:
        query_address = hotel.address or hotel.location or hotel.name
        geocode = geocode_address(query_address, city=city)
        if geocode is None:
            return False
        hotel.address = geocode.get("formatted_address") or hotel.address
        hotel.latitude = geocode.get("latitude")
        hotel.longitude = geocode.get("longitude")
        return True

    hotel.address = place.get("address") or hotel.address
    hotel.latitude = place.get("latitude")
    hotel.longitude = place.get("longitude")
    return True

def _enrich_transport(transport: TransportItem, city: str | None = None) -> bool:
    """补全单段交通：出发地/目的地分别地理编码，再算路线。"""
    # 出发地地理编码
    origin = _pick_best_place(transport.from_place or "", city=city)
    if origin is None:
        geo = geocode_address(transport.from_place or "", city=city)
        origin = {"latitude": geo.get("latitude"), "longitude": geo.get("longitude")} if geo else None
    else:
        origin = {"latitude": origin.get("latitude"), "longitude": origin.get("longitude")}

    # 目的地地理编码
    dest = _pick_best_place(transport.to_place or "", city=city)
    if dest is None:
        geo = geocode_address(transport.to_place or "", city=city)
        dest = {"latitude": geo.get("latitude"), "longitude": geo.get("longitude")} if geo else None
    else:
        dest = {"latitude": dest.get("latitude"), "longitude": dest.get("longitude")}

    if not origin or not dest:
        return False
    if origin.get("latitude") is None or origin.get("longitude") is None:
        return False
    if dest.get("latitude") is None or dest.get("longitude") is None:
        return False

    route = estimate_route(
        origin_longitude=origin["longitude"],
        origin_latitude=origin["latitude"],
        destination_longitude=dest["longitude"],
        destination_latitude=dest["latitude"],
    )
    if route is None:
        return False

    transport.distance_km = route.get("distance_km")
    transport.estimated_minutes = route.get("estimated_minutes")
    if route.get("estimated_minutes") is not None and not transport.duration:
        transport.duration = f"{route['estimated_minutes']} 分钟"
    return True

def enrich_itinerary_with_map_data(itinerary: Itinerary, city: str | None = None) -> Itinerary:
    """
    遍历 itinerary，给每个景点/酒店/交通补全地图数据。

    这是 map_service 的主入口，由 trip_service.py 调用。
    """
    if not ENABLE_AMAP_ENRICHMENT:
        logger.info("地图补全已关闭（ENABLE_AMAP_ENRICHMENT=false）")
        return itinerary

    if not AMAP_API_KEY:
        logger.warning("未配置 AMAP_API_KEY，跳过地图补全")
        return itinerary

    enriched_count = 0
    target_city = city or itinerary.destination

    for day in itinerary.days:
        # 景点
        for spot in day.spots:
            try:
                if _enrich_spot(spot, city=target_city):
                    enriched_count += 1
            except Exception as e:
                logger.warning("景点补全失败 [%s]: %s", spot.name, e)

        # 酒店
        if day.hotel is not None:
            try:
                if _enrich_hotel(day.hotel, city=target_city):
                    enriched_count += 1
            except Exception as e:
                logger.warning("酒店补全失败 [%s]: %s", day.hotel.name, e)

        # 交通
        for transport in day.transport:
            try:
                if _enrich_transport(transport, city=target_city):
                    enriched_count += 1
            except Exception as e:
                logger.warning("交通补全失败: %s", e)

    if enriched_count > 0:
        note = "已补充高德地图地址、坐标或路线估算信息。"
        if note not in itinerary.source_notes:
            itinerary.source_notes.append(note)

    print(f"[Map] 地图补全完成，成功补全 {enriched_count} 个点位")
    return itinerary