"""
query_rewriter.py — 查询改写（规则版）

职责：把用户的口语化输入，改写成向量检索友好的关键词组合。

为什么需要改写？
→ 用户说"不想太赶，想看日落"，直接拿这句话去检索，语义太分散。
  改写成"日落 景点 推荐"后，检索更精准。

本阶段用规则实现（不调用 LLM），阶段10会换成 LLM 改写。
规则思路：
1. 去停用词（的、了、想、不想、太、去...）
2. 提取目的地关键词
3. 提取意图关键词（日落、日出、美食、住宿...）
4. 组合成检索查询
"""
from __future__ import annotations

import re

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

def rewrite_query(user_input: str, destination: str = "") -> str:
    """
    规则级查询改写。

    参数：
        user_input: 用户的原始输入，如 "不想太赶，想看日落"
        destination: 目的地（中文），如 "大理"

    返回：
        改写后的检索查询，如 "大理 日落 景点 推荐"
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

def extract_destination(text: str) -> str | None:
    """
    从用户输入中尝试识别目的地城市。

    返回中文城市名（如"大理"），识别不到返回 None。
    """
    for city_name in CITY_ALIASES:
        if city_name in text:
            return city_name
    return None