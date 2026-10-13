"""方案模式论文·图表体检 —— 对一个（或几个）已落库任务检查图片引用质量。

用法（在 backend/ 目录下）：
    python scripts/check_paper_figures.py                 # 最近 5 个有论文的任务
    python scripts/check_paper_figures.py d20f5bee 12df70f4

检查两件事，并用**定稿闸门本身**（不是另写一套判断）给出"如果现在跑会怎样"：
  ① 引用了不存在的图 → 破图；DOCX 导出时该行会退化成正文文字（内部 API 路径）
  ② 同一张图被重复插入 → 版面凑数；删除前必须确认读者能按编号找到首次出现处

为什么值得留一个脚本：论文是交付物，出问题时需要能直接对**真实落库结果**
复盘，而不是只靠单测里的构造样例。2026-10 的两个真实缺陷
（12df70f4 编造图引用、d20f5bee 重复插图 + 图号错乱）都是这样查出来的。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.api.tasks import _resolve_image_path  # noqa: E402
from app.core.node_helpers import (  # noqa: E402
    dedupe_repeated_image_refs,
    strip_missing_image_refs,
)
from app.services.md_docx import markdown_to_docx  # noqa: E402

SESSIONS = BACKEND / "data" / "sessions.json"
IMG_REF_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def docx_api_paths(markdown: str) -> int:
    """DOCX 交付物里残留 `/api/task_files/` 的段落数（破图的可见度）。"""
    from docx import Document

    doc = Document()
    markdown_to_docx(doc, markdown, image_resolver=_resolve_image_path)
    return sum(1 for p in doc.paragraphs if "/api/task_files/" in p.text)


def check(task_id: str, sessions: dict) -> str:
    paper = (sessions.get(task_id) or {}).get("final_response") or ""
    if not paper:
        return f"{task_id}: 没有 final_response（未完成或非方案模式）"

    refs = IMG_REF_RE.findall(paper)
    fixed, missing = strip_missing_image_refs(paper)
    fixed, duplicates = dedupe_repeated_image_refs(fixed)
    refs_after = IMG_REF_RE.findall(fixed)

    lines = [
        f"{task_id}:",
        f"  原始   {len(paper):>6} 字符 · 图片引用 {len(refs)} 处 / 去重 {len(set(refs))} 张",
        f"  闸门①  删除不存在的引用 {len(missing)} 处" + (f" {missing}" if missing else ""),
        f"  闸门②  删除重复引用     {len(duplicates)} 处",
        f"  定稿   {len(fixed):>6} 字符 · 图片引用 {len(refs_after)} 处 / 去重 {len(set(refs_after))} 张",
        f"  DOCX 残留内部路径段落：{docx_api_paths(paper)} → {docx_api_paths(fixed)}",
    ]
    if len(refs_after) != len(set(refs_after)):
        lines.append(
            f"  ⚠ 仍有 {len(refs_after) - len(set(refs_after))} 处重复引用被保留"
            "（编号对不上，删除会变成错误引用 —— 交给红队/人工改图号）"
        )
    return "\n".join(lines)


def main() -> None:
    sessions = json.loads(SESSIONS.read_text(encoding="utf-8"))
    if len(sys.argv) > 1:
        task_ids = sys.argv[1:]
    else:
        with_paper = [
            (t.get("updated_at") or "", tid)
            for tid, t in sessions.items()
            if t.get("final_response")
        ]
        task_ids = [tid for _, tid in sorted(with_paper, reverse=True)[:5]]
        print(f"（未指定任务，体检最近 {len(task_ids)} 个有论文的任务）\n")
    for tid in task_ids:
        print(check(tid, sessions))
        print()


if __name__ == "__main__":
    main()
