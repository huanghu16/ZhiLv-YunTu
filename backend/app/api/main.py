"""
main.py — FastAPI 应用入口

职责：
1. 创建 FastAPI 应用实例
2. 注册所有路由（trip / export / weather 等）
3. 配置 CORS（允许前端跨域访问）
4. 启动时自动创建数据库表

启动方式：
    cd backend
    uvicorn app.api.main:app --reload --port 8000

启动后访问：
    http://localhost:8000/docs  → 自动生成的 API 文档（Swagger UI）
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 导入路由
from app.api.routes import trip
from app.api.routes import export  # 阶段8新增：文档导出路由

# 导入数据库配置（阶段7会用到，这里先导入确保 Base 被加载）
from app.config import Base, engine

def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用。

    用工厂函数模式创建 app，方便测试时创建不同配置的实例。
    """
    app = FastAPI(
        title="智旅云图 API",
        description="基于 RAG + LLM 的 AI 旅行规划系统",
        version="0.7.0",  # 阶段8，修改版本为 0.7.0
    )

    # ── CORS 配置 ──────────────────────────────────────
    # CORS = 跨域资源共享。前端（localhost:5173）调后端（localhost:8000），
    # 端口不同就是"跨域"，浏览器会拦截。CORS 中间件允许指定来源访问。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],        # 开发阶段允许所有来源，生产环境要限定
        allow_credentials=True,
        allow_methods=["*"],        # 允许所有 HTTP 方法
        allow_headers=["*"],        # 允许所有请求头
    )

    # ── 注册路由 ──────────────────────────────────────
    # prefix: 所有 /trips 开头的路由都转到 trip.router
    app.include_router(trip.router, prefix="/api/trips", tags=["行程管理"])
    # 阶段8新增：文档导出路由
    # 访问路径：/api/export/{trip_id}/markdown 或 /api/export/{trip_id}/pdf
    app.include_router(export.router, prefix="/api/export", tags=["文档导出"])

    # ── 健康检查 ──────────────────────────────────────
    @app.get("/health", tags=["系统"])
    async def health_check():
        """健康检查接口，用于确认服务是否在线。"""
        return {"status": "ok", "service": "zhilv-yuntu"}

    return app

# 创建全局 app 实例（uvicorn 通过模块路径找到它）
app = create_app()

# 启动时自动创建数据库表（阶段7会填充真正的表结构）
# Base.metadata.create_all 会根据继承 Base 的模型自动建表
# 当前还没有模型，这行不会报错也不会建任何表
Base.metadata.create_all(bind=engine)