"""方案模式交付物一致性单测 —— 论文图片引用校验 / 结构统计 / 最新文件选择。

背景（真实证据，非假想）：
  · 任务 12df70f4 的论文正文引用了 `/api/task_files/12df70f4/q4_pareto--8f3a1c.png`，
    但该文件在求解/验证材料与文件区里都不存在（写作模型照抄哈希命名规律编出来的）。
    网页阅读器是一张破图，DOCX 导出这一行会原样落成正文文字。
  · 任务 222e0839 的 tool_result.images 里同一张图出现两次
    （`[q2_route.png, q2_route.png]`），前端会渲染两遍。
  · 同一任务产出过两份结果表（`results--634f20b5.xlsx` / `results--0d33e0a5.xlsx`），
    导出按字典序取，与生成顺序无关。
"""

from __future__ import annotations

from pathlib import Path

from app.api.tasks import _latest_task_file
from app.config import get_settings
from app.core.node_helpers import (
    _collect_file_urls,
    _collect_image_urls,
    count_paper_structure,
    resolve_task_media_path,
    strip_missing_image_refs,
)


def _task_dir(task_id: str) -> Path:
    return get_settings().project_root / "data" / "task_files" / task_id


def test_collect_image_urls_dedupes_preserving_order():
    """同一段文本里重复上报的图表 URL → 去重且保持首次出现顺序。"""
    text = (
        "输出:\n/api/images/run1/a.png saved\n"
        "生成图表: /api/images/run1/a.png, /api/images/run1/b.png\n"
    )
    assert _collect_image_urls(text) == [
        "/api/images/run1/a.png",
        "/api/images/run1/b.png",
    ]


def test_collect_file_urls_dedupes():
    text = "生成 Excel 文件: /api/task_files/r1/x.xlsx\n/tapi/task_files/r1/x.xlsx"
    assert _collect_file_urls(text, "xlsx") == ["/api/task_files/r1/x.xlsx"]


def test_resolve_task_media_path_returns_none_for_missing():
    """不存在的图片引用必须解析为 None（校验与 DOCX 插图共用这条判定）。"""
    assert resolve_task_media_path("/api/task_files/no_such_task_xyz/nope.png") is None
    assert resolve_task_media_path("") is None
    assert resolve_task_media_path("/api/task_files") is None


def test_strip_missing_image_refs_removes_ref_and_caption():
    """引用不存在的图 → 连图注一起删；存在的图原样保留。"""
    task_id = "unittest_media_guard"
    d = _task_dir(task_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "real--deadbeef.png").write_bytes(b"png")
    try:
        md = "\n".join(
            [
                "# 论文",
                "",
                "正文一段。",
                "",
                f"![图2](/api/task_files/{task_id}/real--deadbeef.png)",
                "",
                "图 2：真实存在的图",
                "",
                f"![图3](/api/task_files/{task_id}/fake--12345678.png)",
                "图 3：编造出来的图",
                "",
                "结论。",
            ]
        )
        cleaned, dropped = strip_missing_image_refs(md)

        assert dropped == [f"/api/task_files/{task_id}/fake--12345678.png"]
        assert "fake--12345678" not in cleaned
        # 图注一并删除，避免"有图注没图"的悬空描述
        assert "图 3：编造出来的图" not in cleaned
        # 真实图片与其图注保留
        assert "real--deadbeef.png" in cleaned
        assert "图 2：真实存在的图" in cleaned
        assert "结论。" in cleaned
    finally:
        for f in d.glob("*"):
            f.unlink()
        d.rmdir()


def test_strip_missing_image_refs_noop_when_all_resolve():
    md = "无图的一段话\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    cleaned, dropped = strip_missing_image_refs(md)
    assert dropped == []
    assert cleaned == md


def test_count_paper_structure_counts_sections_and_figures():
    md = "\n".join(
        [
            "# 题目",
            "## 一、问题重述",
            "### 1.1 小节",
            "## 二、模型建立",
            "![图1](/api/task_files/t/a.png)",
            "正文",
        ]
    )
    assert count_paper_structure(md) == (3, 1)
    assert count_paper_structure("") == (0, 0)


def test_latest_task_file_prefers_newest_mtime(tmp_path):
    """多轮产物 → 取 mtime 最新那份（字典序与生成顺序无关）。"""
    old = tmp_path / "results--634f20b5.xlsx"
    new = tmp_path / "results--0d33e0a5.xlsx"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    # 让 new 的 mtime 明确晚于 old（文件系统时间精度可能很粗）
    import os
    import time

    now = time.time()
    os.utime(old, (now - 60, now - 60))
    os.utime(new, (now, now))

    assert _latest_task_file(tmp_path, "*.xlsx") == new
    assert _latest_task_file(tmp_path, "*.csv") is None


def test_docx_export_has_no_raw_image_markdown_after_strip():
    """端到端：剥离缺失图片引用后导出 DOCX，交付物里不再出现原始 API 路径。

    这是「破图」问题的交付物侧证据：md_docx 解析不到本地文件时，这一行会
    退化成普通文字落进 Word——实测文本形如
    `图3：图片: /api/task_files/…/q4_pareto--8f3a1c.png）`，
    评委翻开看到的是一行内部路径而不是图。
    """
    from docx import Document

    from app.api.tasks import _resolve_image_path
    from app.services.md_docx import markdown_to_docx

    missing = "![图3](/api/task_files/222e0839/q4_pareto--8f3a1c.png)"
    md = f"# 标题\n\n正文。\n\n{missing}\n图 4.1：不存在的图\n\n结尾。\n"

    # 未清理：图片解析不到本地路径 → 内部 API 路径原样落进 Word（缺陷现场）
    doc = Document()
    markdown_to_docx(doc, md, image_resolver=_resolve_image_path)
    raw_text = "\n".join(p.text for p in doc.paragraphs)
    assert "/api/task_files/" in raw_text

    # 清理后：图片引用与图注都不再出现，正文其余内容完好
    cleaned, dropped = strip_missing_image_refs(md)
    assert dropped == ["/api/task_files/222e0839/q4_pareto--8f3a1c.png"]
    doc2 = Document()
    markdown_to_docx(doc2, cleaned, image_resolver=_resolve_image_path)
    clean_text = "\n".join(p.text for p in doc2.paragraphs)
    assert "/api/task_files/" not in clean_text
    assert "图 4.1" not in clean_text
    assert "正文。" in clean_text
    assert "结尾。" in clean_text
