"""
trip.py — 行程管理路由（阶段7更新）

新增接口：
    GET  /{trip_id}   查询单个行程
    GET  /            查询行程列表
    DELETE /{trip_id} 删除行程（新增）
    GET  /token-stats  token 统计（新增）
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    Itinerary,
    TokenStatsResponse,
    TripEditRequest,
    TripListResponse,
    TripRequest,
    TripSaveRequest,
)
from app.services.storage_service import (
    delete_trip,
    get_token_stats,
    get_trip,
    list_trips,
    save_trip,
)
from app.services.trip_service import edit_trip, plan_trip

router = APIRouter()

@router.post("/generate", response_model=Itinerary)
async def generate_trip(request: TripRequest):
    """生成新行程，并自动保存到数据库。"""
    try:
        itinerary = plan_trip(request)
        # 生成后自动保存
        save_trip(itinerary)
        return itinerary
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"行程生成失败: {e}")

@router.post("/edit", response_model=Itinerary)
async def edit_existing_trip(request: TripEditRequest):
    """编辑已有行程，并更新数据库。"""
    try:
        itinerary = edit_trip(
            trip_id=request.trip_id,
            current_itinerary=request.current_itinerary,
            user_instruction=request.user_instruction,
            edit_scope=request.edit_scope,
            preserve_constraints=request.preserve_constraints,
        )
        # 编辑后自动保存
        save_trip(itinerary)
        return itinerary
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"行程编辑失败: {e}")

@router.post("/save", response_model=Itinerary)
async def save_existing_trip(request: TripSaveRequest):
    """手动保存行程（不生成，只存储）。"""
    try:
        save_trip(request.itinerary)
        return request.itinerary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"行程保存失败: {e}")

@router.get("/{trip_id}", response_model=Itinerary)
async def get_trip_by_id(trip_id: str):
    """按 ID 查询单个行程。"""
    itinerary = get_trip(trip_id)
    if not itinerary:
        raise HTTPException(status_code=404, detail=f"行程不存在: {trip_id}")
    return itinerary

@router.get("/", response_model=TripListResponse)
async def get_trip_list(
    destination: str | None = Query(default=None, description="按目的地筛选"),
    limit: int = Query(default=20, ge=1, le=100, description="每页数量"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
):
    """查询行程列表，支持按目的地筛选和分页。"""
    items, total = list_trips(destination=destination, limit=limit, offset=offset)
    return TripListResponse(total=total, items=items)

@router.delete("/{trip_id}")
async def delete_trip_by_id(trip_id: str):
    """删除行程。"""
    success = delete_trip(trip_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"行程不存在: {trip_id}")
    return {"message": f"行程已删除: {trip_id}"}

#注意路由顺序：/token-stats/summary 必须放在 /{trip_id} 之前定义，否则 FastAPI 会把 token-stats 当成 trip_id 去匹配。
@router.get("/token-stats/summary", response_model=TokenStatsResponse)
async def get_token_summary():
    """查询所有行程的 token 消耗统计。"""
    items = get_token_stats()
    total_prompt = sum(item.token_usage.total_prompt_tokens for item in items)
    total_completion = sum(item.token_usage.total_completion_tokens for item in items)
    return TokenStatsResponse(
        trip_count=len(items),
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_tokens=total_prompt + total_completion,
        items=items,
    )