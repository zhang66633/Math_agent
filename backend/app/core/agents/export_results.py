"""Export results agent node - deliverable collection and export.

Split from core/nodes.py: nodes.py keeps only orchestration nodes
(classify/retrieve/plan/format_response) plus re-exports.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage

from app.config import get_settings
from app.core.state import AgentState

from ..node_helpers import (
    _check_cancelled,
    _next_step,
    _pub_event,
    logger,
)


def export_results_agent_node(state: AgentState) -> dict:
    """结果导出 Agent — 将求解结果打包为结构化文件。

    仅在 execute 模式时执行。
    - 收集求解阶段产出的 xlsx/csv/html 文件
    - 用 ResultPackager 生成汇总 xlsx 和 zip 包
    """
    idx = _next_step(state)
    task_id = state["session_id"]
    _check_cancelled(task_id)

    _pub_event(task_id, "node_start", "export_results_agent", {"step": idx + 1})
    settings = get_settings()

    export_files: list[dict] = []
    try:
        from app.services.result_packager import ResultPackager

        packager = ResultPackager(task_id, settings.project_root)

        # 生成汇总 xlsx
        solving_output = state.get("solving_output") or ""
        summary_xlsx = packager.build_summary_xlsx(
            solving_output=solving_output,
            task_files_dir=packager.task_dir,
        )
        if summary_xlsx.exists():
            export_files.append(
                {
                    "type": "xlsx",
                    "name": summary_xlsx.name,
                    "url": f"/api/task_files/{task_id}/{summary_xlsx.name}",
                    "size": summary_xlsx.stat().st_size,
                }
            )

        # 打包 zip
        zip_path = packager.build_zip_package()
        if zip_path.exists():
            export_files.append(
                {
                    "type": "zip",
                    "name": zip_path.name,
                    "url": f"/api/task_files/{task_id}/{zip_path.name}",
                    "size": zip_path.stat().st_size,
                }
            )
    except Exception as e:
        logger.warning("结果导出失败: %s", e)

    _pub_event(
        task_id,
        "node_end",
        "export_results_agent",
        {
            "step": idx + 1,
            "files_count": len(export_files),
            "summary": f"生成 {len(export_files)} 个导出文件",
            "title": "结果导出",
            "desc": f"导出 {len(export_files)} 个文件" if export_files else "导出失败",
        },
    )

    return {
        "export_files": export_files,
        "current_step_index": idx,
        "messages": [
            SystemMessage(content=f"[导出Agent] 第{idx + 1}步完成，导出 {len(export_files)} 个文件")
        ],
    }


# ============================================================
# 节点: 格式化输出
# ============================================================
