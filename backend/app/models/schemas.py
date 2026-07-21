"""
schemas.py — 全项目的数据模型字典（Pydantic）

Pydantic 是什么？
→ 一个数据校验库。你定义一个类继承 BaseModel，它就会自动：
  1. 校验传入数据是否符合类型（比如 budget 必须是数字且 >=0）
  2. 自动生成 JSON Schema（FastAPI 据此生成接口文档）
  3. 支持序列化/反序列化（Python 对象 ↔ JSON）

本文件定义了"一次旅行"的完整数据结构：
  TripRequest（用户输入）→ 拆成 DayPlan（每天安排）
    → 每个 DayPlan 含 SpotItem（景点）/ MealItem（餐饮）/ HotelItem（住宿）/ TransportItem（交通）
    → 多个 DayPlan 组成 Itinerary（完整行程）
"""
from __future__ import annotations

from datetime import date as DateType, datetime

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════
# 一、用户请求模型（输入）
# ═══════════════════════════════════════════════════════════

class TripRequest(BaseModel):
    """用户生成新行程时的请求体。"""

    destination: str = Field(..., description="目的地，例如大理")
    start_date: DateType = Field(..., description="出行开始日期")
    end_date: DateType = Field(..., description="出行结束日期")
    travelers: int = Field(..., ge=1, description="出行人数，至少 1")
    budget: float = Field(..., ge=0, description="总预算（元）")
    preferences: list[str] = Field(default_factory=list, description="旅行偏好标签，如 自然风景、美食")
    pace: str | None = Field(default=None, description="节奏：轻松 / 适中 / 紧凑")
    dietary_preferences: list[str] = Field(default_factory=list, description="饮食偏好或忌口")
    hotel_level: str | None = Field(default=None, description="酒店档次：经济型 / 舒适型 / 高档")
    special_notes: str | None = Field(default=None, description="额外要求，如 想看日落")

class TripEditRequest(BaseModel):
    """用户修改已有行程时的请求体（阶段6用到）。"""

    trip_id: str = Field(..., description="需要编辑的行程 ID")
    current_itinerary: "Itinerary" = Field(..., description="当前完整行程")
    user_instruction: str = Field(..., description="用户新的修改要求")
    edit_scope: str | None = Field(default=None, description="编辑范围，如 day_1")
    preserve_constraints: list[str] = Field(default_factory=list, description="需保留的条件")

class TripSaveRequest(BaseModel):
    """保存行程时的请求体（阶段7用到）。"""

    trip_id: str = Field(..., description="行程 ID")
    itinerary: "Itinerary" = Field(..., description="完整行程数据")
    user_id: str | None = Field(default=None, description="用户 ID，当前版本可留空")

# ═══════════════════════════════════════════════════════════
# 二、行程构建块（单个景点 / 餐饮 / 住宿 / 交通）
# ═══════════════════════════════════════════════════════════

class SpotItem(BaseModel):
    """单个景点安排。"""

    name: str = Field(..., description="景点名称")
    start_time: str | None = Field(default=None, description="开始时间")
    end_time: str | None = Field(default=None, description="结束时间")
    description: str | None = Field(default=None, description="景点说明")
    estimated_cost: float = Field(default=0.0, ge=0, description="预估门票花费")
    location: str | None = Field(default=None, description="位置描述")
    # 以下字段由地图服务填充（阶段9/地图阶段），暂时为空
    image_url: str | None = Field(default=None, description="景点图片")
    address: str | None = Field(default=None, description="详细地址")
    latitude: float | None = Field(default=None, description="纬度")
    longitude: float | None = Field(default=None, description="经度")
    poi_id: str | None = Field(default=None, description="地图 POI 标识")

class MealItem(BaseModel):
    """单个餐饮安排。"""

    name: str = Field(..., description="餐厅或餐饮名称")
    meal_type: str = Field(..., description="早餐 / 午餐 / 晚餐")
    estimated_cost: float = Field(default=0.0, ge=0, description="预估花费")
    notes: str | None = Field(default=None, description="补充说明")

class HotelItem(BaseModel):
    """单个住宿安排。"""

    name: str = Field(..., description="酒店名称")
    level: str | None = Field(default=None, description="档次")
    estimated_cost: float = Field(default=0.0, ge=0, description="预估花费")
    location: str | None = Field(default=None, description="位置")
    address: str | None = Field(default=None, description="详细地址")
    latitude: float | None = Field(default=None, description="纬度")
    longitude: float | None = Field(default=None, description="经度")

class TransportItem(BaseModel):
    """单段交通安排。"""

    mode: str = Field(..., description="交通方式：步行 / 打车 / 公交")
    from_place: str | None = Field(default=None, description="出发地")
    to_place: str | None = Field(default=None, description="目的地")
    estimated_cost: float = Field(default=0.0, ge=0, description="预估花费")
    duration: str | None = Field(default=None, description="预计耗时，如 30 分钟")
    distance_km: float | None = Field(default=None, ge=0, description="预计距离（公里）")
    estimated_minutes: int | None = Field(default=None, ge=0, description="预计耗时（分钟）")

# ═══════════════════════════════════════════════════════════
# 三、聚合模型（单日 / 预算 / 完整行程）
# ═══════════════════════════════════════════════════════════

class BudgetBreakdown(BaseModel):
    """预算拆分。"""

    transport: float = Field(default=0.0, ge=0, description="交通预算")
    hotel: float = Field(default=0.0, ge=0, description="住宿预算")
    meals: float = Field(default=0.0, ge=0, description="餐饮预算")
    tickets: float = Field(default=0.0, ge=0, description="门票预算")
    other: float = Field(default=0.0, ge=0, description="其他预算")
    total: float = Field(default=0.0, ge=0, description="预算总计")

class DayPlan(BaseModel):
    """单日行程安排。"""

    day_index: int = Field(..., ge=1, description="第几天，从 1 开始")
    date: DateType | None = Field(default=None, description="当天日期")
    theme: str | None = Field(default=None, description="当天主题")
    spots: list[SpotItem] = Field(default_factory=list, description="景点安排")
    meals: list[MealItem] = Field(default_factory=list, description="餐饮安排")
    hotel: HotelItem | None = Field(default=None, description="住宿安排")
    transport: list[TransportItem] = Field(default_factory=list, description="交通安排")
    notes: list[str] = Field(default_factory=list, description="补充说明")

class TokenUsage(BaseModel):
    """LLM 调用的 token 消耗统计（阶段4/10用到）。记录每次行程生成花了多少 token。"""

    rewrite_prompt_tokens: int = Field(default=0, ge=0, description="Query Rewrite 输入 token")
    rewrite_completion_tokens: int = Field(default=0, ge=0, description="Query Rewrite 输出 token")
    embedding_prompt_tokens: int = Field(default=0, ge=0, description="Embedding 输入 token")
    embedding_completion_tokens: int = Field(default=0, ge=0, description="Embedding 输出 token")
    planner_prompt_tokens: int = Field(default=0, ge=0, description="行程生成输入 token")
    planner_completion_tokens: int = Field(default=0, ge=0, description="行程生成输出 token")
    rerank_prompt_tokens: int = Field(default=0, ge=0, description="Rerank 输入 token")
    rerank_completion_tokens: int = Field(default=0, ge=0, description="Rerank 输出 token")

    @property
    def total_prompt_tokens(self) -> int:
        """所有环节的输入 token 总和。"""
        return (
            self.rewrite_prompt_tokens
            + self.embedding_prompt_tokens
            + self.planner_prompt_tokens
            + self.rerank_prompt_tokens
        )

    @property
    def total_completion_tokens(self) -> int:
        """所有环节的输出 token 总和。"""
        return (
            self.rewrite_completion_tokens
            + self.embedding_completion_tokens
            + self.planner_completion_tokens
            + self.rerank_completion_tokens
        )

    @property
    def total_tokens(self) -> int:
        """总 token。"""
        return self.total_prompt_tokens + self.total_completion_tokens

class Itinerary(BaseModel):
    """完整行程。这是整个项目最核心的数据结构。"""

    trip_id: str = Field(..., description="行程唯一标识")
    destination: str = Field(..., description="目的地")
    summary: str = Field(..., description="整趟行程概述")
    days: list[DayPlan] = Field(default_factory=list, description="逐日行程")
    estimated_budget: float = Field(default=0.0, ge=0, description="预算总计")
    budget_breakdown: BudgetBreakdown = Field(..., description="预算明细")
    tips: list[str] = Field(default_factory=list, description="旅行建议")
    source_notes: list[str] = Field(default_factory=list, description="RAG 来源说明")
    token_usage: TokenUsage | None = Field(default=None, description="token 消耗统计")

# ═══════════════════════════════════════════════════════════
# 四、接口响应模型（阶段6/7用到）
# ═══════════════════════════════════════════════════════════

class TripDetailResponse(BaseModel):
    """查询已保存行程时的响应。"""

    trip_id: str
    itinerary: Itinerary
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)

class TripSummaryItem(BaseModel):
    """历史列表中单条行程的摘要。"""

    trip_id: str
    destination: str
    summary: str
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)

class TripListResponse(BaseModel):
    """行程列表响应。"""

    total: int = Field(..., ge=0)
    items: list[TripSummaryItem] = Field(default_factory=list)

class TripTokenStatsItem(BaseModel):
    """单条行程的 token 统计。"""

    trip_id: str
    destination: str
    token_usage: TokenUsage

class TokenStatsResponse(BaseModel):
    """token 统计汇总响应。"""

    trip_count: int = Field(..., ge=0)
    total_prompt_tokens: int = Field(default=0, ge=0)
    total_completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    items: list[TripTokenStatsItem] = Field(default_factory=list)

# 解决前向引用：TripEditRequest / TripSaveRequest 里用了 "Itinerary"（字符串），
# 这里把它们关联起来，让 Pydantic 能正确解析
TripEditRequest.model_rebuild()
TripSaveRequest.model_rebuild()