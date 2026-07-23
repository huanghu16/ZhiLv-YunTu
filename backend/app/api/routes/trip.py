"""
trip.py — 行程管理路由

职责：
    定义行程相关的 HTTP 接口。路由层是"薄层"，
    只做：接收请求 → 校验参数 → 调用 service → 返回结果。
    不写业务逻辑（业务逻辑全在 trip_service 里）。

接口列表：
    POST /generate   生成新行程
    POST /edit       编辑已有行程
    GET  /{trip_id}  查询单个行程（阶段7实现存储后生效）
    GET  /           查询行程列表（阶段7实现存储后生效）
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    Itinerary,
    TripEditRequest,
    TripRequest,
)
from app.services.trip_service import edit_trip, plan_trip

# 创建路由器。APIRouter 是 FastAPI 的路由分组工具。
# 每个路由文件创建自己的 router，在 main.py 里统一注册。
router = APIRouter()

@router.post("/generate", response_model=Itinerary)
async def generate_trip(request: TripRequest):
    """
    生成新行程。

    接收用户需求（目的地、日期、预算、偏好等），
    返回结构化的完整行程。

    - **request**: TripRequest 对象，FastAPI 自动校验参数
    - **返回**: Itinerary 对象，FastAPI 自动序列化为 JSON

    耗时说明：这个接口会调用 LLM，通常需要 10-60 秒。
    """
    try:
        itinerary = plan_trip(request)
        return itinerary
    except ValueError as e:
        # 参数校验类错误 → 400
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 其他错误 → 500
        raise HTTPException(status_code=500, detail=f"行程生成失败: {e}")

@router.post("/edit", response_model=Itinerary)
async def edit_existing_trip(request: TripEditRequest):
    """
    编辑已有行程。

    接收当前行程 + 修改要求，返回修改后的完整行程。
    """
    try:
        itinerary = edit_trip(
            trip_id=request.trip_id,
            current_itinerary=request.current_itinerary,
            user_instruction=request.user_instruction,
            edit_scope=request.edit_scope,
            preserve_constraints=request.preserve_constraints,
        )
        return itinerary
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"行程编辑失败: {e}")

# ── 以下接口需要存储层支持，阶段7实现后生效 ──────────────────

@router.get("/{trip_id}", response_model=Itinerary)
async def get_trip(trip_id: str):
    """
    查询单个行程。

    阶段7实现 SQLite 存储后，这里会从数据库读取。
    当前返回 501 Not Implemented。
    """
    raise HTTPException(
        status_code=501,
        detail="行程查询功能将在阶段7（持久化）实现",
    )

@router.get("/", response_model=dict)
async def list_trips():
    """
    查询行程列表。

    阶段7实现 SQLite 存储后，这里会从数据库读取列表。
    当前返回 501 Not Implemented。
    """
    raise HTTPException(
        status_code=501,
        detail="行程列表功能将在阶段7（持久化）实现",
    )