"""上传文件解析器 — PDF(文本/OCR/渲染) / Excel / CSV / DOCX / 多模态消息。

从 api/knowledge_search_routes.py 拆出（该路由文件曾把 270 行文件格式
解析塞在 18 个路由中间，职责错位）。本模块只依赖标准库 + 惰性 import
的重依赖（pdfplumber/pymupdf/rapidocr/pandas/python-docx），按需加载。

异常契约：解析失败抛 HTTPException（400=内容问题，500=缺依赖）——路由层
原样透传，调用方无需再包一层。服务层直接用 HTTP 异常是本项目路由密集
场景下的务实选择（调用方全是 FastAPI 路由）。
"""

from __future__ import annotations

from fastapi import HTTPException


def ocr_pdf_text(file_bytes: bytes) -> str:
    """对扫描版/无文字层 PDF 做 OCR 提取（pymupdf 渲染 + RapidOCR）。"""

    try:
        import fitz  # pymupdf
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="扫描版 PDF 需要 OCR 支持，请安装: pip install pymupdf rapidocr_onnxruntime",
        )

    try:
        import numpy as np

        ocr = RapidOCR()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            # RapidOCR 接受 BGR/灰度，统一转 3 通道
            if pix.n == 4:  # RGBA -> RGB
                img = img[:, :, :3]
            result, _ = ocr(img)
            if result:
                pages.append("\n".join(line[1] for line in result))
        return "\n\n".join(pages)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF OCR 失败: {e}")


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from a PDF byte stream.

    优先用 pdfplumber（对表格、多栏版面支持更好），缺失时回退 PyPDF2；
    若文字层提取为空（扫描版 PDF），自动转 OCR。
    """
    import io

    extracted = ""

    # 首选 pdfplumber
    try:
        import pdfplumber

        pages = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        extracted = "\n\n".join(pages)
    except ImportError:
        pass  # 回退到 PyPDF2
    except Exception:
        # pdfplumber 解析异常时也尝试 PyPDF2 兜底
        pass

    # 回退 PyPDF2
    if not extracted.strip():
        try:
            import PyPDF2

            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            extracted = "\n\n".join(pages)
        except ImportError:
            pass
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"PDF 解析失败: {e}")

    # 文字层为空 → 扫描版 PDF，转 OCR
    if not extracted.strip():
        extracted = ocr_pdf_text(file_bytes)

    if not extracted.strip():
        raise HTTPException(
            status_code=400, detail="PDF 未提取到任何文本（可能为纯图片且 OCR 无结果）"
        )

    return extracted


def pdf_to_images(file_bytes: bytes, max_pages: int = 20) -> list[str]:
    """PDF → 每页一张 PNG base64。pymupdf 渲染，保留公式、图表、代码等视觉元素。

    限制 max_pages + 较低 dpi 防止超大 PDF 撑爆视觉模型 payload(常见上限 ~10MB)。
    """
    import base64

    import fitz

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF 打开失败: {e}")

    pages = min(len(doc), max_pages)
    images: list[str] = []
    for i in range(pages):
        page = doc[i]
        pix = page.get_pixmap(dpi=110)
        img_b64 = base64.b64encode(pix.tobytes("png")).decode()
        images.append(img_b64)

    doc.close()
    return images


def build_multimodal_message(
    text_content: str, images_base64: list[str], provider: str = "openai"
):
    """构建多模态 HumanMessage：文本指令 + 图片(data URI 或裸 PNG base64)。

    如果 images_base64 为空，返回纯文本消息。
    provider 决定图片块格式: openai → image_url data URI;anthropic → image 块。
    """
    from langchain_core.messages import HumanMessage

    if not images_base64:
        return HumanMessage(content=text_content)

    content: list[dict] = [{"type": "text", "text": text_content}]
    for img in images_base64:
        if provider == "anthropic":
            # 解析 data URI(data:image/<mime>;base64,<b64>),旧裸 base64 按 PNG 处理
            mime, b64 = "png", img
            if img.startswith("data:"):
                head, _, b64 = img.partition(",")
                mime = head.split(";")[0].split("/")[-1]
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": f"image/{mime}",
                        "data": b64,
                    },
                }
            )
        else:
            # 已带 data: 前缀的 data URI 直接使用(上传层已编码),裸 base64 补前缀
            url = img if img.startswith("data:") else f"data:image/png;base64,{img}"
            content.append({"type": "image_url", "image_url": {"url": url}})

    return HumanMessage(content=content)


# ── file type parsers ──────────────────────────────────────────────


def parse_excel(file_bytes: bytes, filename: str) -> str:
    """Excel (.xlsx/.xls) → 结构化文本摘要。

    每个 sheet 输出: 行列数、列名、前20行数据、数值列统计信息。
    """
    import io

    import pandas as pd

    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    parts = [f"[Excel: {filename}] 共 {len(xls.sheet_names)} 个工作表"]

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        parts.append(f"\n--- 工作表: {sheet_name} ---")
        parts.append(f"维度: {df.shape[0]} 行 × {df.shape[1]} 列")
        parts.append(f"列名: {list(df.columns)}")

        if df.shape[0] > 0:
            # Show first 20 rows
            parts.append(f"\n前 {min(20, df.shape[0])} 行数据:")
            try:
                parts.append(df.head(20).to_string(index=False))
            except Exception:
                parts.append(str(df.head(20)))

            # Statistical summary for numeric columns
            num_cols = df.select_dtypes(include="number").columns
            if len(num_cols) > 0:
                parts.append("\n数值列统计摘要:")
                try:
                    parts.append(df[num_cols].describe().to_string())
                except Exception:
                    pass

    return "\n".join(parts)


def parse_csv(file_bytes: bytes, filename: str) -> str:
    """CSV → 结构化文本摘要。"""
    import io

    import pandas as pd

    # Try common encodings
    for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
            break
        except (UnicodeDecodeError, Exception):
            continue
    else:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8", errors="replace")

    parts = [
        f"[CSV: {filename}]",
        f"维度: {df.shape[0]} 行 × {df.shape[1]} 列",
        f"列名: {list(df.columns)}",
    ]

    if df.shape[0] > 0:
        parts.append(f"\n前 {min(20, df.shape[0])} 行:")
        try:
            parts.append(df.head(20).to_string(index=False))
        except Exception:
            parts.append(str(df.head(20)))

    return "\n".join(parts)


def extract_docx_text(file_bytes: bytes) -> str:
    """Extract text from a DOCX byte stream（段落 + 表格，按文档顺序）。"""
    try:
        import io

        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = docx.Document(io.BytesIO(file_bytes))
        parts: list[str] = []

        def _iter_block_items(document):
            """按文档顺序产出段落和表格对象。"""
            from docx.oxml.ns import qn

            for child in document.element.body.iterchildren():
                if child.tag == qn("w:p"):
                    yield Paragraph(child, document)
                elif child.tag == qn("w:tbl"):
                    yield Table(child, document)

        for block in _iter_block_items(doc):
            if isinstance(block, Paragraph):
                if block.text.strip():
                    parts.append(block.text)
            elif isinstance(block, Table):
                for row in block.rows:
                    cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                    if any(cells):
                        parts.append(" | ".join(cells))

        return "\n".join(parts)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="DOCX 提取需要安装 python-docx: pip install python-docx",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DOCX 解析失败: {e}")
