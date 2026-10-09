"""Analysis agent node - problem decomposition, type detection, method recommendation.

Split from core/nodes.py: nodes.py keeps only orchestration nodes
(classify/retrieve/plan/format_response) plus re-exports.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.state import AgentState

from ..llm.factory import get_llm
from ..node_helpers import (
    _check_cancelled,
    _log_usage,
    _next_step,
    _pub_event,
    _save_working_memory,
    invoke_streaming_with_retry,
)
from ..prompts.analysis import (
    ANALYSIS_SYSTEM_PROMPT,
    ANALYSIS_TEACH_SYSTEM_PROMPT,
    ANALYSIS_TEACH_USER_TEMPLATE,
    ANALYSIS_USER_TEMPLATE,
)


def analysis_agent_node(state: AgentState) -> dict:
    """问题分析 Agent — 用 LLM 深度分析问题结构。"""
    idx = _next_step(state)
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "analysis_agent", {"step": idx + 1})
    llm = get_llm("analysis", state.get("api_key_config"))

    # 构建知识库上下文
    methods_str = (
        "\n".join(
            f"- **{m['name']}**: {m.get('principle', '')[:200]}" for m in state["kb_methods"][:5]
        )
        or "（无推荐方法）"
    )

    templates_str = (
        "\n".join(
            f"- {t['name']}（适用于: {', '.join(t.get('applicable_to', []))}）"
            for t in state["kb_templates"][:3]
        )
        or "（无匹配模板）"
    )

    if state["mode"] == "teach":
        system_prompt = ANALYSIS_TEACH_SYSTEM_PROMPT.format(
            methods=methods_str,
            templates=templates_str,
        )
        user_prompt = ANALYSIS_TEACH_USER_TEMPLATE.format(
            problem=state["problem_raw"],
            problem_type=state["problem_type"],
        )
    else:
        system_prompt = ANALYSIS_SYSTEM_PROMPT.format(
            methods=methods_str,
            templates=templates_str,
        )
        user_prompt = ANALYSIS_USER_TEMPLATE.format(
            problem=state["problem_raw"],
            problem_type=state["problem_type"],
        )

    # 流式输出：逐 chunk 推 node_delta 事件（前端像 chat 一样逐字渲染）
    analysis_output, usage = invoke_streaming_with_retry(
        llm,
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ],
        task_id=task_id,
        node="analysis_agent",
    )
    _log_usage(task_id, "analysis", usage)

    _pub_event(
        task_id,
        "node_end",
        "analysis_agent",
        {
            "step": idx + 1,
            "output_length": len(analysis_output),
            "summary": analysis_output[:800],
            "title": "问题分析",
            "desc": f"深度分析问题结构，输出 {len(analysis_output)} 字",
        },
    )

    if state["mode"] == "execute":
        _save_working_memory(task_id, "analysis", analysis_output)

    return {
        "analysis_output": analysis_output,
        "current_step_index": idx,
        "messages": [
            SystemMessage(content=f"[分析Agent] 第{idx + 1}步完成，输出 {len(analysis_output)} 字")
        ],
    }


