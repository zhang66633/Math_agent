"""交互工具集：ask_user（澄清需求）+ run_code（代码执行）。

ask_user:
    LLM 判断用户问题模糊时调用，前端渲染选项卡片让用户选择。
    后端不执行此工具——检测到后直接发 clarify SSE 帧并结束本轮流。

run_code:
    复用 SandboxExecutor 在受限子进程中执行 Python 代码，
    返回 stdout + 生成的图片路径。供 chat/teach 模式使用。
    支持 file_ids：将用户上传的文件复制到沙箱工作目录。
    支持 data_files_dir：自动挂载题目数据文件目录到沙箱。
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import ClassVar

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .base import TOOL_DEFAULTS

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# AskUserTool — 向用户提出澄清问题（前端渲染选项卡片）
# ────────────────────────────────────────────────────────────────────


class ClarifyOption(BaseModel):
    label: str = Field(description="选项显示文本（简短）")
    description: str = Field(default="", description="选项补充说明")


class ClarifyQuestion(BaseModel):
    question: str = Field(description="要向用户提出的问题")
    options: list[ClarifyOption] = Field(description="2-4 个选项")
    multiSelect: bool = Field(default=False, description="是否允许多选")


class AskUserInput(BaseModel):
    questions: list[ClarifyQuestion] = Field(
        description="1-3 个需要用户确认的问题",
        min_length=1,
        max_length=3,
    )


class AskUserTool(BaseTool):
    """当用户问题信息不足时，调用此工具向用户提出澄清问题。"""

    name: ClassVar[str] = "ask_user"
    description: ClassVar[str] = (
        "当你无法确定用户的具体需求时调用此工具。"
        "例如：用户只说'帮我建模'但没说是什么类型的问题、有什么数据、目标是什么。"
        "提出 1-3 个关键问题，每个问题给 2-4 个选项供用户选择。"
        "注意：如果用户的问题已经足够明确（如'粒子群算法是什么'），不要调用此工具，直接回答。"
    )
    args_schema: type[BaseModel] = AskUserInput

    def _run(self, questions: list, run_manager: CallbackManagerForToolRun | None = None) -> str:
        # 此工具不会被后端真正执行——chat_routes 检测到后直接发 clarify 帧
        # 这里只是 fallback（理论上不会走到）
        return json.dumps({"questions": questions}, ensure_ascii=False)


# ────────────────────────────────────────────────────────────────────
# RunCodeTool — 在沙箱中执行 Python 代码
# ────────────────────────────────────────────────────────────────────


class RunCodeInput(BaseModel):
    code: str = Field(
        description=(
            "要执行的 Python 代码。可以使用 numpy, scipy, matplotlib, pandas, sympy 等库。"
            "matplotlib 图表会自动保存为 PNG。"
            "用 print() 输出关键结果。"
            "如果用户上传了文件，文件会被复制到当前工作目录，直接用文件名读取即可。"
        )
    )
    file_ids: list[str] = Field(
        default=[],
        description="需要复制到沙箱工作目录的已上传文件 ID 列表（来自用户上传的附件）。",
    )


class RunCodeTool(BaseTool):
    """在安全沙箱中执行 Python 代码，返回输出结果和生成的图表。"""

    name: ClassVar[str] = "run_code"
    description: ClassVar[str] = (
        "执行 Python 代码进行数值计算、数据分析或绘图。"
        "适用场景：验证公式、数值求解、画函数图/统计图、处理数据文件。"
        "代码中可用: numpy, scipy, matplotlib, pandas, sympy, cvxpy。"
        "matplotlib 图表会自动保存并返回路径。"
        "**数据文件已自动挂载到工作目录，直接用 pd.read_parquet('文件名') 读取，不需要传 file_ids。**"
        "**OCR 提取文字（扫描版 PDF/图片）**：可用 rapidocr_onnxruntime（import rapidocr_onnxruntime，"
        "纯 Python 中英文 OCR，无需外部命令）或 pytesseract（import pytesseract，已配置中英文）。"
        "PDF 每页转图片用 pymupdf（import fitz）或 pdf2image。"
    )
    args_schema: type[BaseModel] = RunCodeInput

    # ── 安全默认值（借鉴 cc-haha）──
    is_concurrency_safe: bool = False  # 代码执行有副作用，不可并发
    is_read_only: bool = False
    is_destructive: bool = False
    max_result_chars: int = TOOL_DEFAULTS["max_result_chars"]

    # ── 可选：题目数据文件目录（由求解节点注入）──
    data_files_dir: str = ""

    # ── 可选：任务取消事件（由编排节点注入；置位时中断沙箱执行，事件级取消）──
    cancel_event: threading.Event | None = None

    def _run(
        self,
        code: str,
        file_ids: list[str] | None = None,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        from ..config import get_settings
        from ..sandbox.executor import SandboxExecutor

        executor = SandboxExecutor()

        # 解析 file_ids → 上传目录中的绝对路径
        extra_files: list[str] = []
        if file_ids:
            settings = get_settings()
            uploads_dir = (settings.project_root / "data" / "uploads").resolve()
            for fid in file_ids:
                # 路径穿越防护（AGENTS.md 红线）：file_id 只允许 [a-zA-Z0-9._-]，
                # 拒绝点号段/斜杠/反斜杠；resolve 后必须仍在 uploads_dir 内
                if (
                    not isinstance(fid, str)
                    or not fid
                    or not re.fullmatch(r"[a-zA-Z0-9._-]+", fid)
                    or set(fid) <= {"."}
                ):
                    logger.warning("非法 file_id 已拒绝: %r", fid)
                    continue
                matches = list(uploads_dir.glob(f"{fid}.*"))
                if not matches:
                    logger.warning("file_id %s 在上传目录中未找到", fid)
                    continue
                resolved = Path(matches[0]).resolve()
                if not resolved.is_relative_to(uploads_dir):
                    logger.warning("file_id 越界已拒绝: %s", fid)
                    continue
                extra_files.append(str(resolved))

        # 自动挂载题目数据文件（如果设置了 data_files_dir）
        if self.data_files_dir:
            data_dir = Path(self.data_files_dir)
            if data_dir.exists():
                for f in data_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in (
                        ".xlsx",
                        ".xls",
                        ".csv",
                        ".tsv",
                        ".txt",
                        ".json",
                        ".dat",
                        # 2026-10-14 补：.parquet 与 .md。项目自带的 2023C 数据
                        # （含 87.8 万行销售明细与一批 _precomputed_*.parquet 聚合）
                        # 全是 parquet，DATA_README.md 也是照着「沙箱里
                        # pd.read_parquet()」设计的——但这两个后缀一直不在白名单里，
                        # 于是那套预计算数据从未真正进过沙箱。
                        ".parquet",
                        ".md",
                    ):
                        extra_files.append(str(f))
                        logger.info("自动挂载数据文件: %s", f.name)

        result = executor.run(code, extra_files=extra_files or None, cancel_event=self.cancel_event)

        parts = []
        if result["stdout"]:
            parts.append(f"输出:\n{result['stdout']}")
        # 失败必须无条件输出错误段（审查 A）：RLIMIT_CPU 杀进程等场景 stderr
        # 为空，旧实现静默吞掉失败 → LLM 把部分输出当成功结果写进报告
        if not result["success"]:
            err = result.get("stderr") or (
                f"进程异常退出 (returncode={result.get('returncode')})，无 stderr 输出"
            )
            parts.append(f"错误:\n{err}")
            if result["stdout"]:
                parts.append(
                    "注意：以上输出产生于失败/超时之前，不是完整结果，禁止直接当作最终数值。"
                )
        if result["images"]:
            # 去重保序：同一个 run 里同一张图可能被 executor 重复上报
            # （stdout 打印路径 + 文件列表收集各一次），实测事件流里
            # images 出现过 [q2_route.png, q2_route.png]——前端按 URL 渲染会让
            # 同一张图出现两遍（用户看到的"图表重复"）。源头去重，下游不必各自兜。
            img_urls = list(
                dict.fromkeys(
                    f"/api/images/{result['run_id']}/{Path(img_path).name}"
                    for img_path in result["images"]
                )
            )
            parts.append(f"生成图表: {', '.join(img_urls)}")
        if result.get("xlsx_files"):
            xlsx_urls = list(
                dict.fromkeys(
                    f"/api/task_files/{result['run_id']}/{Path(fpath).name}"
                    for fpath in result["xlsx_files"]
                )
            )
            parts.append(f"生成 Excel 文件: {', '.join(xlsx_urls)}")
        if result.get("csv_files"):
            csv_urls = list(
                dict.fromkeys(
                    f"/api/task_files/{result['run_id']}/{Path(fpath).name}"
                    for fpath in result["csv_files"]
                )
            )
            parts.append(f"生成 CSV 文件: {', '.join(csv_urls)}")
        if result.get("html_files"):
            html_urls = list(
                dict.fromkeys(
                    f"/api/task_files/{result['run_id']}/{Path(fpath).name}"
                    for fpath in result["html_files"]
                )
            )
            parts.append(f"生成 HTML 报告: {', '.join(html_urls)}")
        if not parts:
            parts.append("代码执行完成，无输出。")

        return "\n".join(parts)


# ────────────────────────────────────────────────────────────────────
# 工厂函数
# ────────────────────────────────────────────────────────────────────


def create_interaction_tools() -> list:
    """创建交互工具列表。"""
    return [AskUserTool(), RunCodeTool()]
