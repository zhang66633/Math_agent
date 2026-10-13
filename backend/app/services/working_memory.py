"""工作记忆 — 方案模式问题状态文档 + 阶段检查点。

每个 solution 会话维护:
  - problem_doc.md:       问题状态文档（由各阶段检查点**确定性拼装**，无 LLM 调用）
  - checkpoints/*.json:   每个阶段独立的检查点（可恢复）
  - meta.json:            会话元数据（原始问题等，供拼装时引用）

设计参考: MEMORY_CONTEXT_GUIDE.md §5.1 / §5.3
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── 阶段顺序映射 ────────────────────────────────────────────

STAGE_ORDER = [
    "classify",
    "retrieve",
    "analysis",
    "modeling",
    "solving",
    "verification",
    "writing",
]

STAGE_LABELS = {
    "classify": "一、问题分类",
    "retrieve": "二、知识检索",
    "analysis": "三、问题分析",
    "modeling": "四、模型建立",
    "solving": "五、求解计算",
    "verification": "六、验证分析",
    "writing": "七、论文写作",
}

def _strip_leading_heading(text: str | None) -> str:
    """去掉摘要自带的一级/二级标题行。

    章节名（`## 三、问题分析`）已经由拼装层给出，而各节点产出常以自己的
    `## 问题分析` 开头，直接拼会出现两级同名标题。只去**开头连续**的标题行，
    不动正文里的标题。
    """
    lines = (text or "").strip().splitlines()
    while lines and lines[0].lstrip().startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()


# ── 废弃实现的墓碑（为什么没有 LLM 重写版了） ─────────────────
# 曾经有一版「LLM 整体重写问题状态文档」的实现（REWRITE_PROMPT +
# update_problem_doc），已删除。原因记录在此，免得后人重新踩：
#
#   1. 它靠 `asyncio.get_event_loop().run_in_executor(...)` 异步触发，而图节点
#      跑在 langgraph 的线程池 worker 里——那些线程没有运行中的事件循环，
#      get_event_loop() 恒抛 RuntimeError，被 except 静默跳过。生产环境里
#      从未生效过一次（审计 2026-10-14 实证：所有真实任务的 problem_doc.md
#      都是 init_session 写的初始模板，七个章节全「（待完成）」）。
#   2. 即使修好机制，它每个阶段要多打一次 LLM（约 7 次/任务），而当时
#      get_problem_doc() 全仓库零调用方——花了钱没人看。
#
# 现在的实现是确定性拼装（见 refresh_problem_doc）：只读检查点 JSON，纯文件 IO，
# 可同步调用，并通过 GET /api/tasks/{id}/status 的 problem_doc 字段暴露给前端。


class WorkingMemory:
    """方案模式会话的工作记忆管理器。"""

    def __init__(self, session_id: str):
        settings = get_settings()
        self.session_id = session_id
        self.session_dir = settings.project_root / "data" / "sessions" / session_id
        self.checkpoints_dir = self.session_dir / "checkpoints"
        self.problem_doc_path = self.session_dir / "problem_doc.md"
        self.meta_path = self.session_dir / "meta.json"

    # ── 初始化 ──────────────────────────────────────────────

    def init_session(self, problem_raw: str) -> None:
        """新建会话目录 + 初始 problem_doc + meta。"""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        # meta：拼装 problem_doc 时要引用原始问题（曾被 init_session 写进模板后
        # 就再也读不回来，因为模板会被 refresh 覆盖）。
        self._atomic_write_json(
            self.meta_path,
            {
                "session_id": self.session_id,
                "problem_raw": problem_raw,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

        if not self.problem_doc_path.exists():
            self._atomic_write(self.problem_doc_path, self._render_doc({}))

    # ── 检查点 ──────────────────────────────────────────────

    def save_checkpoint(self, stage: str, output: str, extra: dict | None = None) -> Path:
        """保存阶段检查点，并连带刷新问题状态文档。返回 checkpoint 文件路径。

        刷新放在这里而不是交给调用方：否则「存了检查点但忘了刷文档」会让
        problem_doc.md 悄悄过期——那正是死功能时代的症状。检查点写成功是硬保证，
        文档刷新失败只告警（不阻塞主流程）。
        """
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "stage": stage,
            "stage_label": STAGE_LABELS.get(stage, stage),
            "timestamp": datetime.now(UTC).isoformat(),
            "output_summary": output[:500],
            "output": output,
            **(extra or {}),
        }
        path = self.checkpoints_dir / f"{stage}.json"
        self._atomic_write_json(path, data)
        try:
            self.refresh_problem_doc()
        except Exception as e:  # noqa: BLE001
            logger.warning("检查点已保存，但问题状态文档刷新失败 (%s): %s", self.session_id, e)
        return path

    def load_checkpoint(self, stage: str) -> dict | None:
        """加载指定阶段的检查点。"""
        path = self.checkpoints_dir / f"{stage}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("检查点损坏: %s", path)
            return None

    def get_completed_stages(self) -> list[str]:
        """返回已完成的阶段列表（有序）。"""
        completed = []
        for stage in STAGE_ORDER:
            if (self.checkpoints_dir / f"{stage}.json").exists():
                completed.append(stage)
        return completed

    def get_latest_stage(self) -> str | None:
        """返回最新已完成的阶段名。"""
        completed = self.get_completed_stages()
        return completed[-1] if completed else None

    def get_resume_stage(self) -> str | None:
        """返回应该从哪个阶段恢复（最新完成阶段的下一个）。"""
        completed = self.get_completed_stages()
        if not completed:
            return None
        last = completed[-1]
        try:
            idx = STAGE_ORDER.index(last)
            if idx + 1 < len(STAGE_ORDER):
                return STAGE_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    # ── 问题状态文档 ────────────────────────────────────────

    def get_problem_doc(self) -> str:
        """读取当前问题状态文档。"""
        if self.problem_doc_path.exists():
            return self.problem_doc_path.read_text(encoding="utf-8")
        return ""

    def _load_meta(self) -> dict:
        if not self.meta_path.exists():
            return {}
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _render_doc(self, summaries: dict[str, str]) -> str:
        """把各阶段摘要拼成问题状态文档（纯函数，便于测试）。"""
        lines = ["# 问题状态文档", ""]
        for stage in STAGE_ORDER:
            lines.append(f"## {STAGE_LABELS[stage]}")
            lines.append(_strip_leading_heading(summaries.get(stage)) or "（待完成）")
            lines.append("")
        problem_raw = (self._load_meta().get("problem_raw") or "").strip()
        if problem_raw:
            lines.append("---")
            lines.append("")
            lines.append("**原始问题**:")
            lines.append(problem_raw[:500])
            lines.append("")
        return "\n".join(lines)

    def refresh_problem_doc(self) -> str:
        """用各阶段检查点重新拼装问题状态文档并落盘，返回新内容。

        确定性实现，**不调 LLM**：取代已废弃的 LLM 整体重写版
        （废弃原因见文件顶部「墓碑」注释——那版在生产环境从未生效过）。
        纯文件 IO，可在节点线程里同步调用；没有检查点时就当不存在，直接返回。
        """
        if not self.problem_doc_path.exists():
            return ""
        summaries = {
            stage: (cp.get("output_summary") or "").strip()
            for stage in STAGE_ORDER
            if (cp := self.load_checkpoint(stage))
        }
        new_doc = self._render_doc(summaries)
        self._atomic_write(self.problem_doc_path, new_doc)
        return new_doc

    # ── 会话状态 ────────────────────────────────────────────

    def is_active(self) -> bool:
        """检查会话是否存在未完成的任务。"""
        if not self.problem_doc_path.exists():
            return False
        completed = self.get_completed_stages()
        return len(completed) > 0 and len(completed) < len(STAGE_ORDER)

    # ── 工具方法 ────────────────────────────────────────────

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """原子写入：先写 .tmp 再 rename，崩溃不留残骸。"""
        tmp = path.with_suffix(".tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        """原子写入 JSON。"""
        tmp = path.with_suffix(".tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
