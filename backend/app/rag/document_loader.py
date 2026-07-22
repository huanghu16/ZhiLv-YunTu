"""
document_loader.py — 文档加载与切块

职责：
1. 读取 data/ 目录下所有 Markdown 攻略
2. 按三级标题（###）把长文档切成小块（chunk）
3. 给每个 chunk 打上元数据标签（city、source、heading）

为什么按 ### 切而不是 ## 切？
→ 攻略的 ## 下有多个 ###（如"景点推荐"下有"洱海""苍山"等）。
  按 ### 切能让每个景点独立成块，检索更精准。
  按 ## 切会把所有景点混在一块，语义太杂。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config import BACKEND_DIR

@dataclass
class DocumentChunk:
    """一个文档切块。dataclass 是 Python 的轻量级数据类。"""

    chunk_id: str          # 唯一标识，如 "dali_洱海"
    content: str           # 切块正文
    city: str              # 城市，如 "dali"
    source: str            # 来源文件名，如 "dali_guide.md"
    heading: str           # 所属标题，如 "洱海"
    section: str           # 所属大类，如 "景点推荐"
    metadata: dict = field(default_factory=dict)  # 额外元数据

def _extract_city_name(filename: str) -> str:
    """从文件名提取城市名。dali_guide.md → dali"""
    return filename.replace(".md", "").split("_")[0]

def load_and_split(file_path: Path) -> list[DocumentChunk]:
    """
    读取单个 Markdown 文件，按三级标题切块。

    切块逻辑：
    1. 先按 ## 分大段（景点推荐、美食推荐、交通...），记录所属大类
    2. 每个大段内再按 ### 切成独立小块（洱海、苍山...）
    3. 没有 ### 子标题的大段（如旅行贴士）整体作为一块
    """
    city = _extract_city_name(file_path.name)
    source = file_path.name
    text = file_path.read_text(encoding="utf-8")

    chunks: list[DocumentChunk] = []

    # 第一步：按 ## 分割，拿到每个大类
    # (?=^## ) 正向预查，保留分隔符
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)

    for section_text in sections:
        section_text = section_text.strip()
        if not section_text:
            continue

        # 提取大类名（## 标题）
        first_line = section_text.split("\n", 1)[0]
        if first_line.startswith("# ") and not first_line.startswith("## "):
            # 一级标题（# 大理旅游攻略），作为城市概述
            section_name = "城市概述"
        elif first_line.startswith("## "):
            section_name = re.sub(r"^##\s*", "", first_line).strip()
        else:
            section_name = "未分类"

        # 第二步：在大段内按 ### 切子块
        sub_parts = re.split(r"(?=^### )", section_text, flags=re.MULTILINE)

        has_sub_heading = False
        for sub_text in sub_parts:
            sub_text = sub_text.strip()
            if not sub_text:
                continue

            if sub_text.startswith("### "):
                # 有 ### 子标题的块（如 ### 洱海）
                has_sub_heading = True
                heading = re.sub(r"^###\s*", "", sub_text.split("\n", 1)[0]).strip()
            else:
                # 没有 ### 的部分（大段开头、旅行贴士等）
                # 如果这个大段有 ### 子块，跳过开头的引言部分
                if has_sub_heading or section_text.startswith("### "):
                    continue
                heading = section_name

            chunk_id = f"{city}_{section_name}_{heading}"

            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    content=sub_text,
                    city=city,
                    source=source,
                    heading=heading,
                    section=section_name,
                    metadata={
                        "city": city,
                        "source": source,
                        "heading": heading,
                        "section": section_name,
                    },
                )
            )

    return chunks

def load_all_guides(data_dir: Path | None = None) -> list[DocumentChunk]:
    """
    加载 data/ 目录下所有 Markdown 攻略，返回全部切块。
    """
    if data_dir is None:
        data_dir = BACKEND_DIR / "data"

    md_files = sorted(data_dir.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"在 {data_dir} 没有找到 Markdown 文件")

    all_chunks: list[DocumentChunk] = []
    for md_file in md_files:
        chunks = load_and_split(md_file)
        all_chunks.extend(chunks)
        print(f"  {md_file.name}: 切出 {len(chunks)} 块")

    print(f"共加载 {len(all_chunks)} 个文档切块")
    return all_chunks

if __name__ == "__main__":
    chunks = load_all_guides()
    print("\n=== 前 5 个切块预览 ===")
    for c in chunks[:5]:
        print(f"\n[{c.chunk_id}] city={c.city} section={c.section} heading={c.heading}")
        print(c.content[:100] + "...")