"""导出接口 — Markdown → DOCX。

转换实现已抽到 `app/services/md_docx.py`（单一真源）。此前 `api/tasks.py` 里还有一份
**会跳过表格**的简化实现，同一篇论文走两个入口导出的结果不一致。

本模块只保留 HTTP 层。历史私有名 `_parse_inline` / `_is_table_separator` / `_markdown_to_docx`
继续 re-export，保持既有 import 路径与测试可用。
"""

import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.md_docx import (
    _is_table_separator,  # noqa: F401  re-export，保持历史 import 路径
    _markdown_to_docx,  # noqa: F401  re-export
    _parse_inline,  # noqa: F401  re-export
    content_disposition,
    markdown_to_docx,
)

export_router = APIRouter()


class ExportDocxRequest(BaseModel):
    markdown: str
    title: str = "对话记录"


@export_router.post("/export/docx")
async def export_docx(req: ExportDocxRequest):
    """将 Markdown 文本转为 .docx 文件下载。"""
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise HTTPException(status_code=500, detail="python-docx 未安装")

    doc = Document()

    # 标题
    heading = doc.add_heading(req.title, level=0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    markdown_to_docx(doc, req.markdown)

    # 输出为流
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    # 中文标题不能直接进 HTTP 头（Starlette 按 latin-1 编码会抛 UnicodeEncodeError，
    # 实测任何中文标题都返回 500）；改用 RFC 5987 的 filename* 形式。
    filename = f"{req.title}.docx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": content_disposition(filename, fallback="export.docx")},
    )
