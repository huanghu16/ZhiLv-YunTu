"""
config.py — 全局配置中心

职责：
1. 加载 .env 环境变量
2. 初始化 SQLite 数据库连接（SQLAlchemy）
3. 集中管理 LLM / RAG / Redis / 高德地图 的配置项

为什么单独抽一个 config.py？
→ 让所有模块从同一个地方读取配置，避免配置散落各处。
  修改 .env 就能调整行为，不用改代码。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ─── 1. 定位 backend 目录，加载 .env ──────────────────────────
# __file__ 是 config.py 自己，往上两级就是 backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# ─── 2. SQLite 数据库配置 ─────────────────────────────────────
# SQLite 是单文件数据库，适合个人项目和 Demo，无需单独安装服务
DB_DIR = BACKEND_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)  # 目录不存在就自动创建

SQLITE_DB_PATH = DB_DIR / "app.db"
DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH.as_posix()}"

# create_engine 创建数据库连接引擎
# check_same_thread=False：允许跨线程访问（FastAPI 会用线程池）
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base 是所有数据库表的基类，db_models.py（阶段7）会继承它
Base = declarative_base()

# ─── 3. 大模型（LLM）配置 ────────────────────────────────────
# 项目用 DashScope（阿里云通义千问），它提供 OpenAI 兼容接口
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-max")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))

# ─── 4. RAG / 向量库配置 ─────────────────────────────────────
# ChromaDB 是轻量级本地向量数据库，数据存在 db/chroma_db 目录
_chroma_db_dir_raw = Path(os.getenv("CHROMA_DB_DIR", "db/chroma_db"))
CHROMA_DB_DIR = (
    _chroma_db_dir_raw
    if _chroma_db_dir_raw.is_absolute()
    else BACKEND_DIR / _chroma_db_dir_raw
)
CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "travel_guides")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "10"))
RERANK_MODEL = os.getenv("RERANK_MODEL", "qwen3-rerank")

# ─── 5. Redis / 缓存配置 ─────────────────────────────────────
# Redis 缓存天气、地图、RAG 结果，减少重复外部调用
# REDIS_ENABLED=false 时自动降级，不缓存也能正常运行
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "trip_planner")
REDIS_DEFAULT_TTL_SECONDS = int(os.getenv("REDIS_DEFAULT_TTL_SECONDS", "1800"))
REDIS_WEATHER_TTL_SECONDS = int(os.getenv("REDIS_WEATHER_TTL_SECONDS", "1800"))
REDIS_MAP_TTL_SECONDS = int(os.getenv("REDIS_MAP_TTL_SECONDS", "86400"))
REDIS_RAG_TTL_SECONDS = int(os.getenv("REDIS_RAG_TTL_SECONDS", "21600"))
REDIS_RERANK_TTL_SECONDS = int(os.getenv("REDIS_RERANK_TTL_SECONDS", "21600"))

# ─── 6. 高德地图配置 ─────────────────────────────────────────
# 高德地图补充景点地址、经纬度、路线、图片
# 暂时没有 Key，ENABLE_AMAP_ENRICHMENT=false，不影响核心功能
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
AMAP_BASE_URL = os.getenv("AMAP_BASE_URL", "https://restapi.amap.com/v3")
AMAP_DEFAULT_CITY = os.getenv("AMAP_DEFAULT_CITY", "")
AMAP_TIMEOUT_SECONDS = int(os.getenv("AMAP_TIMEOUT_SECONDS", "20"))
ENABLE_AMAP_ENRICHMENT = os.getenv("ENABLE_AMAP_ENRICHMENT", "false").lower() == "true"