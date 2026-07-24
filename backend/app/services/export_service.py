"""
export_service.py — 文档导出服务（阶段8）

职责：
    把 Itinerary（行程数据对象）转换成两种可分享的文档格式：
    1. Markdown：纯文本，方便在 GitHub / 博客 / 笔记软件里查看
    2. PDF：带排版的正式文档，方便打印和分享给朋友

为什么需要导出？
→ 用户生成的行程存在数据库里是 JSON 格式，普通人看不懂。
  导出成 Markdown / PDF 后，用户可以直接拿去用。

核心函数：
    - itinerary_to_markdown(itinerary) -> str   返回 Markdown 文本
    - itinerary_to_pdf_bytes(itinerary) -> bytes 返回 PDF 二进制数据

设计要点：
    - 导出的是"给用户看的文档"，所以要过滤掉内部实现细节
      （比如 token 统计、RAG 调试信息），只保留旅行相关内容
    - PDF 需要中文字体支持，使用 reportlab 内置的 STSong-Light
"""
from __future__ import annotations

from io import BytesIO
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

from app.models.schemas import Itinerary


# ─── 内部关键词过滤 ──────────────────────────────────────────
# 这些关键词出现在 tips / source_notes 里时，说明是后端调试信息，
# 不应该出现在用户看到的导出文档里
_TECHNICAL_KEYWORDS = (
    "LLM", "RAG", "LangChain", "Chroma", "token",
    "演示", "测试", "规则", "模型", "源码", "trip_service",
    "Query Rewrite", "Rerank", "embedding",
)


def _is_technical_text(text: str) -> bool:
    """判断一段文字是否是技术/调试信息（需要过滤掉）。"""
    return any(keyword in text for keyword in _TECHNICAL_KEYWORDS)


def _filter_public_tips(tips: list[str]) -> list[str]:
    """过滤旅行提示，只保留用户可读的内容，去重。"""
    cleaned: list[str] = []
    for tip in tips:
        tip = tip.strip()
        if not tip:
            continue
        if _is_technical_text(tip):
            continue
        if tip not in cleaned:
            cleaned.append(tip)
    return cleaned


def _filter_public_notes(source_notes: list[str]) -> list[str]:
    """过滤来源说明，只保留用户可读的攻略来源。"""
    cleaned: list[str] = []
    for note in source_notes:
        note = note.strip()
        if not note:
            continue
        if _is_technical_text(note):
            continue
        if note not in cleaned:
            cleaned.append(note)
    return cleaned


def _safe_text(value: object) -> str:
    """转义 ReportLab Paragraph 里的特殊字符（< > &），避免被当成 XML 标签。"""
    return escape(str(value or ""))


# ═══════════════════════════════════════════════════════════
# 一、Markdown 导出
# ═══════════════════════════════════════════════════════════

def _render_budget_lines(itinerary: Itinerary) -> list[str]:
    """把预算拆分渲染成 Markdown 列表行。"""
    b = itinerary.budget_breakdown
    return [
        f"- 交通：{b.transport:.2f} 元",
        f"- 住宿：{b.hotel:.2f} 元",
        f"- 餐饮：{b.meals:.2f} 元",
        f"- 门票：{b.tickets:.2f} 元",
        f"- 其他：{b.other:.2f} 元",
        f"- **总计：{b.total:.2f} 元**",
    ]


def itinerary_to_markdown(itinerary: Itinerary) -> str:
    """
    把完整行程渲染成 Markdown 文本。

    参数：
        itinerary: Itinerary 对象（从数据库读取或刚生成的）

    返回：
        Markdown 格式的字符串，可直接保存为 .md 文件
    """
    lines: list[str] = [
        f"# {itinerary.destination} 行程单",
        "",
        f"> 行程 ID：`{itinerary.trip_id}`  ",
        f"> 预计预算：**{itinerary.estimated_budget:.2f} 元**",
        "",
        "---",
        "",
        "## 行程概述",
        "",
        itinerary.summary,
        "",
        "## 每日安排",
    ]

    for day in itinerary.days:
        # ── 每日标题 ──
        day_title = f"### Day {day.day_index}"
        if day.theme:
            day_title += f" · {day.theme}"
        lines.extend(["", day_title])

        if day.date:
            lines.append(f"*日期：{day.date.isoformat()}*")
        lines.append("")

        # ── 景点 ──
        if day.spots:
            lines.append("**景点安排：**")
            for spot in day.spots:
                time_range = f"{spot.start_time or '待定'} - {spot.end_time or '待定'}"
                lines.append(f"- **{spot.name}**（{time_range}）")
                if spot.description:
                    lines.append(f"  - {spot.description}")
                if spot.estimated_cost > 0:
                    lines.append(f"  - 预估门票：{spot.estimated_cost:.0f} 元")
                if spot.location:
                    lines.append(f"  - 位置：{spot.location}")
            lines.append("")

        # ── 餐饮 ──
        if day.meals:
            lines.append("**餐饮建议：**")
            for meal in day.meals:
                lines.append(f"- {meal.name}（{meal.meal_type}）")
                if meal.notes:
                    lines.append(f"  - {meal.notes}")
                if meal.estimated_cost > 0:
                    lines.append(f"  - 预估花费：{meal.estimated_cost:.0f} 元")
            lines.append("")

        # ── 住宿 ──
        if day.hotel:
            hotel_line = f"**住宿：** {day.hotel.name}"
            if day.hotel.level:
                hotel_line += f"（{day.hotel.level}）"
            lines.append(hotel_line)
            if day.hotel.estimated_cost > 0:
                lines.append(f"- 预估花费：{day.hotel.estimated_cost:.0f} 元")
            lines.append("")

        # ── 交通 ──
        if day.transport:
            lines.append("**交通安排：**")
            for t in day.transport:
                transport_line = f"- {t.mode}"
                if t.from_place and t.to_place:
                    transport_line += f"：{t.from_place} → {t.to_place}"
                if t.duration:
                    transport_line += f"（{t.duration}）"
                if t.estimated_cost > 0:
                    transport_line += f"，{t.estimated_cost:.0f} 元"
                lines.append(transport_line)
            lines.append("")

        # ── 备注 ──
        if day.notes:
            lines.append("**备注：**")
            for note in day.notes:
                lines.append(f"- {note}")
            lines.append("")

    # ── 预算拆分 ──
    lines.extend(["---", "", "## 预算拆分", "", *_render_budget_lines(itinerary)])

    # ── 旅行提示 ──
    public_tips = _filter_public_tips(itinerary.tips)
    if public_tips:
        lines.extend(["", "## 旅行提示", ""])
        lines.extend(f"- {tip}" for tip in public_tips)

    # ── 攻略来源 ──
    public_notes = _filter_public_notes(itinerary.source_notes)
    if public_notes:
        lines.extend(["", "## 攻略参考", ""])
        lines.extend(f"- {note}" for note in public_notes)

    lines.extend(["", "---", f"*由智旅云图自动生成 | 行程ID: {itinerary.trip_id}*"])

    return "\n".join(lines) + "\n"


# ═══════════════════════════════════════════════════════════
# 二、PDF 导出
# ═══════════════════════════════════════════════════════════

def _register_pdf_font() -> str:
    """
    注册一套支持中文的 PDF 字体。

    ReportLab 内置了 STSong-Light（华文宋体）CID 字体，
    无需额外下载字体文件，适合中文 PDF 生成。

    返回：
        字体名称，后续所有文字都用这个字体
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    font_name = "STSong-Light"
    try:
        # 如果已经注册过，直接用
        pdfmetrics.getFont(font_name)
    except KeyError:
        # 第一次使用时注册
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    return font_name


def _load_spot_image(image_url: str, max_width: float, max_height: float):
    """
    下载景点图片并转换成 ReportLab Image 对象。

    为什么单独抽一个函数？
    → 图片下载可能失败（网络超时、URL 失效），
      失败时返回 None，不影响 PDF 其他部分的生成。

    参数：
        image_url: 图片 URL
        max_width / max_height: 最大宽高（点为单位，1 点 ≈ 0.35mm）

    返回：
        ReportLab Image 对象，或 None（下载失败时）
    """
    from reportlab.platypus import Image

    if not image_url:
        return None

    try:
        request = Request(
            image_url,
            headers={"User-Agent": "TripPlannerDemo/1.0"},
        )
        with urlopen(request, timeout=5) as response:
            # 最多读 2MB，防止超大图片撑爆内存
            image_bytes = response.read(2_000_000)
    except Exception:
        return None

    try:
        image = Image(BytesIO(image_bytes))
        # 按最大宽高等比缩放
        image._restrictSize(max_width, max_height)
        return image
    except Exception:
        return None


def _draw_pdf_footer(canvas, doc, trip_id: str, font_name: str) -> None:
    """
    在每一页底部绘制页脚。

    页脚包含：
    - 分隔线
    - 左下角：行程 ID
    - 右下角：页码

    这是 ReportLab 的回调函数，由 SimpleDocTemplate.build() 在每页绘制时调用。
    """
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    page_width, _ = doc.pagesize
    footer_y = 10 * mm
    line_y = 14 * mm

    canvas.saveState()
    # 分隔线
    canvas.setStrokeColor(colors.HexColor("#cbd2d9"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, line_y, page_width - doc.rightMargin, line_y)

    # 页脚文字
    canvas.setFont(font_name, 9)
    canvas.setFillColor(colors.HexColor("#52606d"))
    canvas.drawString(doc.leftMargin, footer_y, f"智旅云图 | {trip_id}")
    canvas.drawRightString(
        page_width - doc.rightMargin, footer_y, f"第 {canvas.getPageNumber()} 页"
    )
    canvas.restoreState()


def itinerary_to_pdf_bytes(itinerary: Itinerary) -> bytes:
    """
    把完整行程渲染成 PDF 二进制数据。

    参数：
        itinerary: Itinerary 对象

    返回：
        PDF 文件的二进制数据（bytes），可直接作为 HTTP 响应体返回

    技术要点：
    - 使用 reportlab 的 Platypus（Page Layout and Typography Using Scripts）引擎
    - Platypus 用"故事"（Story）模式：把内容拆成一个个元素（Paragraph、Table、Image），
      引擎自动排版分页
    - 中文字体用 STSong-Light，所有文字都要 wordWrap="CJK" 才能正确换行
    """
    # 延迟导入：只有真正生成 PDF 时才加载 reportlab
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PDF 导出依赖 reportlab，请先安装：pip install reportlab"
        ) from exc

    font_name = _register_pdf_font()

    # ── 1. 创建文档对象 ──────────────────────────────────
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,  # 底部留多一点空间给页脚
        title=f"{itinerary.trip_id}.pdf",
    )

    # ── 2. 定义排版样式 ──────────────────────────────────
    # ParagraphStyle = 段落样式，控制字体、字号、颜色、间距等
    base_styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TripTitle",
        parent=base_styles["Title"],
        fontName=font_name,
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#16324f"),
        spaceAfter=8,
        wordWrap="CJK",  # 中文换行模式
    )
    subtitle_style = ParagraphStyle(
        "TripSubtitle",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#4b5d73"),
        spaceAfter=10,
        wordWrap="CJK",
    )
    section_style = ParagraphStyle(
        "TripSection",
        parent=base_styles["Heading2"],
        fontName=font_name,
        fontSize=13.5,
        leading=19,
        textColor=colors.HexColor("#0f4c5c"),
        spaceBefore=10,
        spaceAfter=6,
        wordWrap="CJK",
    )
    day_style = ParagraphStyle(
        "TripDay",
        parent=base_styles["Heading3"],
        fontName=font_name,
        fontSize=12,
        leading=17,
        textColor=colors.HexColor("#1b4332"),
        spaceBefore=6,
        spaceAfter=4,
        wordWrap="CJK",
    )
    body_style = ParagraphStyle(
        "TripBody",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#222222"),
        spaceAfter=4,
        wordWrap="CJK",
    )
    note_style = ParagraphStyle(
        "TripNote",
        parent=body_style,
        leftIndent=8,       # 左缩进，让备注看起来像子项
        bulletIndent=0,
        spaceAfter=3,
    )

    # ── 3. 组装内容（Story）──────────────────────────────
    story = []

    # 标题区
    story.append(Paragraph(f"{_safe_text(itinerary.destination)} 行程单", title_style))
    story.append(
        Paragraph(
            f"行程 ID：{_safe_text(itinerary.trip_id)}<br/>"
            f"预计预算：{itinerary.estimated_budget:.2f} 元<br/>"
            f"行程天数：{len(itinerary.days)} 天",
            subtitle_style,
        )
    )

    # 行程概述
    story.append(Paragraph("行程概述", section_style))
    story.append(Paragraph(_safe_text(itinerary.summary), body_style))

    # 每日安排
    story.append(Paragraph("每日安排", section_style))

    for day in itinerary.days:
        # 日期标题
        day_title = f"Day {day.day_index}"
        if day.theme:
            day_title += f" · {_safe_text(day.theme)}"
        story.append(Paragraph(day_title, day_style))

        if day.date:
            story.append(Paragraph(f"日期：{day.date.isoformat()}", body_style))

        # 景点
        for spot in day.spots:
            story.append(Paragraph(f"景点：{_safe_text(spot.name)}", body_style))

            # 尝试加载景点图片（如果有 image_url）
            spot_image = _load_spot_image(
                spot.image_url or "",
                max_width=72 * mm,
                max_height=42 * mm,
            )
            if spot_image is not None:
                story.extend([spot_image, Spacer(1, 4)])

            story.append(
                Paragraph(
                    f"时间：{_safe_text(spot.start_time or '待定')} - "
                    f"{_safe_text(spot.end_time or '待定')}",
                    note_style,
                )
            )
            if spot.address or spot.location:
                story.append(
                    Paragraph(
                        f"地址：{_safe_text(spot.address or spot.location)}",
                        note_style,
                    )
                )
            if spot.description:
                story.append(
                    Paragraph(f"说明：{_safe_text(spot.description)}", note_style)
                )
            if spot.estimated_cost > 0:
                story.append(
                    Paragraph(f"预估门票：{spot.estimated_cost:.0f} 元", note_style)
                )

        # 餐饮
        for meal in day.meals:
            story.append(
                Paragraph(
                    f"餐饮：{_safe_text(meal.name)}（{_safe_text(meal.meal_type)}）",
                    body_style,
                )
            )
            if meal.notes:
                story.append(Paragraph(f"说明：{_safe_text(meal.notes)}", note_style))
            if meal.estimated_cost > 0:
                story.append(
                    Paragraph(f"预估花费：{meal.estimated_cost:.0f} 元", note_style)
                )

        # 住宿
        if day.hotel:
            hotel_text = f"住宿：{_safe_text(day.hotel.name)}"
            if day.hotel.level:
                hotel_text += f"（{_safe_text(day.hotel.level)}）"
            story.append(Paragraph(hotel_text, body_style))
            if day.hotel.estimated_cost > 0:
                story.append(
                    Paragraph(
                        f"预估花费：{day.hotel.estimated_cost:.0f} 元", note_style
                    )
                )

        # 交通
        for t in day.transport:
            transport_text = f"交通：{_safe_text(t.mode)}"
            if t.from_place and t.to_place:
                transport_text += (
                    f"（{_safe_text(t.from_place)} → {_safe_text(t.to_place)}）"
                )
            if t.duration:
                transport_text += f"，{_safe_text(t.duration)}"
            if t.estimated_cost > 0:
                transport_text += f"，{t.estimated_cost:.0f} 元"
            story.append(Paragraph(transport_text, body_style))

        # 备注
        for note in day.notes:
            story.append(Paragraph(f"备注：{_safe_text(note)}", note_style))

        story.append(Spacer(1, 4))

    # ── 预算拆分表格 ──────────────────────────────────
    story.append(Paragraph("预算拆分", section_style))
    b = itinerary.budget_breakdown
    budget_table = Table(
        [
            ["项目", "金额（元）"],
            ["交通", f"{b.transport:.2f}"],
            ["住宿", f"{b.hotel:.2f}"],
            ["餐饮", f"{b.meals:.2f}"],
            ["门票", f"{b.tickets:.2f}"],
            ["其他", f"{b.other:.2f}"],
            ["总计", f"{b.total:.2f}"],
        ],
        colWidths=[48 * mm, 48 * mm],
    )
    budget_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                # 表头背景色
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9edf7")),
                # 数据行白色背景
                ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                # 总计行强调色
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef6f2")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1f2933")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd2d9")),
                # 金额列右对齐
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([budget_table, Spacer(1, 6)])

    # ── 旅行提示 ──────────────────────────────────────
    public_tips = _filter_public_tips(itinerary.tips)
    if public_tips:
        story.append(Paragraph("旅行提示", section_style))
        for tip in public_tips:
            story.append(Paragraph(f"- {_safe_text(tip)}", body_style))

    # ── 攻略来源 ──────────────────────────────────────
    public_notes = _filter_public_notes(itinerary.source_notes)
    if public_notes:
        story.append(Paragraph("攻略参考", section_style))
        for note in public_notes:
            story.append(Paragraph(f"- {_safe_text(note)}", body_style))

    # ── 4. 生成 PDF ──────────────────────────────────
    # 用闭包把 trip_id 传给页脚回调函数
    def draw_footer(canvas, document) -> None:
        _draw_pdf_footer(canvas, document, itinerary.trip_id, font_name)

    doc.build(
        story,
        onFirstPage=draw_footer,
        onLaterPages=draw_footer,
    )

    # 从 buffer 中取出生成的 PDF 二进制数据
    return buffer.getvalue()
