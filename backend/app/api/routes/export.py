"""
export.py — 文档导出路由（阶段8）

提供两个接口：
    GET /{trip_id}/markdown  → 导出 Markdown 文本
    GET /{trip_id}/pdf       → 导出 PDF 文件

工作流程：
    1. 用户先通过 /api/trips/generate 生成并保存行程
    2. 拿到 trip_id 后，调用导出接口获取文档
    3. 浏览器直接显示或下载文件

为什么用 GET 而不是 POST？
→ 导出是"读取"操作（不修改数据），GET 语义更正确，
  而且浏览器可以直接访问 GET 链接下载文件。
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.services.export_service import (
    itinerary_to_markdown,
    itinerary_to_pdf_bytes,
)
from app.services.storage_service import get_trip

router = APIRouter()


def _build_filename_header(filename: str) -> dict[str, str]:
    """
    生成兼容中文文件名的 Content-Disposition 响应头。

    为什么要特殊处理？
    → HTTP 头只支持 ASCII，中文文件名直接放进去会乱码。
      RFC 5987 规定了 filename*=UTF-8''<url编码> 的格式，
      浏览器会优先解析这个字段，正确显示中文文件名。
    """
    return {
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}"
    }


@router.get("/{trip_id}/markdown", response_class=PlainTextResponse)
async def export_trip_markdown(trip_id: str) -> PlainTextResponse:
    """
    导出行程为 Markdown 文本。

    路径参数：
        trip_id: 行程 ID（从 /api/trips/generate 返回或 /api/trips/ 列表获取）

    返回：
        text/markdown 格式的纯文本，浏览器直接显示
    """
    # 1. 从数据库读取行程
    itinerary = get_trip(trip_id)
    if itinerary is None:
        raise HTTPException(status_code=404, detail=f"行程不存在: {trip_id}")

    # 2. 转换为 Markdown
    markdown_content = itinerary_to_markdown(itinerary)

    # 3. 返回纯文本响应
    return PlainTextResponse(
        content=markdown_content,
        media_type="text/markdown; charset=utf-8",
        headers=_build_filename_header(f"{trip_id}.md"),
    )


@router.get("/{trip_id}/pdf", response_class=Response)
async def export_trip_pdf(trip_id: str) -> Response:
    """
    导出行程为 PDF 文件。

    路径参数：
        trip_id: 行程 ID

    返回：
        application/pdf 格式的二进制文件，浏览器内嵌显示或下载

    可能的错误：
        404: 行程不存在
        503: reportlab 未安装（服务不可用）
    """
    # 1. 从数据库读取行程
    itinerary = get_trip(trip_id)
    if itinerary is None:
        raise HTTPException(status_code=404, detail=f"行程不存在: {trip_id}")

    # 2. 转换为 PDF
    try:
        pdf_bytes = itinerary_to_pdf_bytes(itinerary)
    except RuntimeError as exc:
        # reportlab 未安装时抛出 RuntimeError
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # 3. 返回二进制响应
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_build_filename_header(f"{trip_id}.pdf"),
    )
