"""
query_rewriter.py — 查询改写（阶段10：LLM + 规则降级）

职责：把用户的口语化输入，改写成向量检索友好的关键词组合。

阶段10更新：
    新增 LLM 改写——用通义千问理解用户意图，生成更精准的检索词。
    LLM 调用失败时自动降级到规则版（停用词+关键词映射）。

    为什么 LLM 比规则好？
    → 规则版只能做"关键词替换"，理解不了"带爸妈出去玩"这种复杂意图。
      LLM 能理解"带爸妈"→ 需要亲子/家庭/适老化的景点和住宿。
"""
from __future__ import annotations

import re

from app.config import USE_LLM_REWRITE

# ─── 停用词表 ──────────────────────────────────────────────
# 这些词出现频率高但不携带检索语义，需要去掉
STOP_WORDS = {
    # 助词/语气词
    "的", "了", "吗", "呢", "吧", "啊", "哦", "呀",
    # 动词（口语化，无检索价值）
    "想", "不想", "要", "不要", "需要", "喜欢", "希望",
    "去", "到", "玩", "逛", "吃", "住", "看", "买",
    # 程度/否定词
    "太", "很", "非常", "比较", "有点", "不太", "还行",
    # 连接词
    "和", "与", "及", "或", "但", "但是", "而且", "然后",
    # 时间词（检索攻略不需要）
    "下周", "明天", "今天", "后天", "这个", "下个", "周末",
    # 代词
    "我", "我们", "你", "你们", "他", "她", "他们",
    # 量词/数词相关
    "个", "些", "点", "下", "上", "里",
}

# ─── 意图关键词映射 ─────────────────────────────────────────
# 把用户的口语表达，映射到攻略文档里实际会出现的词
INTENT_KEYWORDS = {
    # 日出日落相关
    "日落": ["日落", "黄昏", "傍晚", "夕阳"],
    "日出": ["日出", "清晨", "早晨"],
    # 节奏相关
    "轻松": ["轻松", "休闲", "散步", "慢"],
    "赶": ["轻松", "休闲"],  # "不想太赶" → 检索轻松类
    # 人群相关
    "爸妈": ["亲子", "家庭", "老人"],
    "孩子": ["亲子", "家庭", "儿童"],
    "老人": ["老人", "亲子", "家庭"],
    # 活动相关
    "拍照": ["拍照", "打卡", "摄影"],
    "美食": ["美食", "小吃", "餐厅"],
    "住宿": ["住宿", "酒店", "客栈"],
    "交通": ["交通", "公交", "打车", "地铁"],
}

# ─── 目的地识别 ─────────────────────────────────────────────
# 从用户输入中识别目的地城市
CITY_ALIASES = {
    "大理": "dali",
    "丽江": "lijiang",
    "成都": "chengdu",
    "杭州": "hangzhou",
    "厦门": "xiamen",
}

# ═══════════════════════════════════════════════════════════
# 规则版改写（原有代码，作为降级方案）
# ═══════════════════════════════════════════════════════════

def _rewrite_by_rules(user_input: str, destination: str = "") -> str:
    """
    规则级查询改写（降级方案）。

    原来的 rewrite_query 逻辑，函数名加下划线表示内部使用。
    """
    # 1. 去除标点符号，统一用空格分词
    cleaned = re.sub(r"[，。！？、；：""''（）()\[\]{}]", " ", user_input)

    # 2. 按空格和常见分隔符切分
    tokens = re.split(r"[\s,，、]+", cleaned.strip())
    tokens = [t for t in tokens if t]  # 去空字符串

    # 3. 去停用词
    filtered = [t for t in tokens if t not in STOP_WORDS]

    # 4. 意图关键词扩展
    # 如果用户说了"日落"，加上"黄昏、傍晚、夕阳"等同义词
    expanded: list[str] = []
    for token in filtered:
        expanded.append(token)
        if token in INTENT_KEYWORDS:
            expanded.extend(INTENT_KEYWORDS[token])

    # 5. 加上目的地
    if destination:
        expanded.insert(0, destination)

    # 6. 去重，保持顺序
    seen: set[str] = set()
    result: list[str] = []
    for word in expanded:
        if word not in seen:
            seen.add(word)
            result.append(word)

    return " ".join(result) if result else user_input

# ═══════════════════════════════════════════════════════════
# LLM 版改写（阶段10新增）
# ═══════════════════════════════════════════════════════════

def _rewrite_by_llm(user_input: str, destination: str = "") -> str:
    """
    LLM 查询改写。

    用通义千问理解用户意图，生成更适合向量检索的关键词组合。

    为什么 LLM 比规则好？
    → "带爸妈去大理，不想太累" ——规则版只会去掉"不想、太"，
      保留"带、爸妈、大理、累"。LLM 能理解这是"亲子/家庭/轻松/休闲"需求。
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.llm_client import get_llm_client

    system_prompt = """你是一个旅行攻略检索的查询改写助手。
用户会给你一段旅行需求描述，你需要：
1. 理解用户的真实意图（亲子？蜜月？摄影？美食？休闲？）
2. 提取目的地
3. 生成 5-8 个适合向量检索的关键词，用空格分隔

要求：
- 只输出关键词，不要输出其他内容
- 关键词要覆盖用户意图的同义词（如"日落"要加"夕阳、黄昏"）
- 不要输出标点符号

示例：
输入：不想太赶，想看日落
输出：大理 日落 夕阳 黄昏 傍晚 景点 推荐 轻松

输入：带爸妈去，不要太累
输出：大理 亲子 家庭 老人 轻松 休闲 适老 景点"""

    human_prompt = f"目的地：{destination}\n用户需求：{user_input}"

    client = get_llm_client()
    content, _ = client.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ])

    # 清理 LLM 输出：去掉可能的换行和多余空格
    rewritten = content.strip().replace("\n", " ")
    rewritten = re.sub(r"\s+", " ", rewritten)

    if not rewritten:
        # LLM 返回空，降级到规则版
        raise ValueError("LLM 返回空结果")

    print(f"[QueryRewrite] LLM 改写: '{user_input}' → '{rewritten}'")
    return rewritten

# ═══════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════

def rewrite_query(user_input: str, destination: str = "") -> str:
    """
    查询改写统一入口。

    优先使用 LLM 改写，失败时降级到规则版。

    参数：
        user_input: 用户的原始输入，如 "不想太赶，想看日落"
        destination: 目的地（中文），如 "大理"

    返回：
        改写后的检索查询，如 "大理 日落 夕阳 黄昏 景点 推荐 轻松"
    """
    # 开关关闭 → 直接用规则版
    if not USE_LLM_REWRITE:
        return _rewrite_by_rules(user_input, destination)

    # 开关开启 → 尝试 LLM，失败降级
    try:
        return _rewrite_by_llm(user_input, destination)
    except Exception as e:
        print(f"[QueryRewrite] LLM 改写失败，降级到规则版: {e}")
        return _rewrite_by_rules(user_input, destination)

def extract_destination(text: str) -> str | None:
    """
    从用户输入中尝试识别目的地城市。

    返回中文城市名（如"大理"），识别不到返回 None。
    """
    for city_name in CITY_ALIASES:
        if city_name in text:
            return city_name
    return None