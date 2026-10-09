"""Modeling agent node - model selection, assumptions, formula derivation.

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
from ..prompts.modeling import (
    MODELING_SYSTEM_PROMPT,
    MODELING_TEACH_SYSTEM_PROMPT,
    MODELING_TEACH_USER_TEMPLATE,
    MODELING_USER_TEMPLATE,
)


def modeling_agent_node(state: AgentState) -> dict:
    """模型构建 Agent — 基于分析结果建立数学模型。"""
    idx = _next_step(state)
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "modeling_agent", {"step": idx + 1})
    llm = get_llm("modeling", state.get("api_key_config"))

    # 构建知识库上下文
    methods_str = (
        "\n".join(f"- **{m['name']}**: {m.get('principle', '')[:200]}" for m in state["kb_methods"])
        or "（无推荐方法）"
    )

    templates_str = "\n".join(f"- {t['name']}" for t in state["kb_templates"]) or "（无匹配模板）"

    if state["mode"] == "teach":
        system_prompt = MODELING_TEACH_SYSTEM_PROMPT.format(
            methods=methods_str,
            templates=templates_str,
        )
        user_prompt = MODELING_TEACH_USER_TEMPLATE.format(
            problem=state["problem_raw"],
            analysis=state.get("analysis_output", "无分析结果"),
            problem_type=state["problem_type"],
        )
    else:
        system_prompt = MODELING_SYSTEM_PROMPT.format(
            methods=methods_str,
            templates=templates_str,
        )
        user_prompt = MODELING_USER_TEMPLATE.format(
            problem=state["problem_raw"],
            analysis=state.get("analysis_output", "无分析结果"),
            problem_type=state["problem_type"],
        )

    # ── 验证反馈闭环（协议 v2.1）：回退重跑时注入上次验证 FAIL 原因，
    #    让建模针对性地修正，而不是盲目重试 ──
    feedback = state.get("verification_feedback")
    if feedback:
        user_prompt += (
            "\n\n## ⚠️ 上次验证未通过（必须针对性修正）\n"
            "以下是你上一版模型的验证反馈，模型存在以下问题，请逐条修正后重新建立模型：\n"
            f"{str(feedback)[:2000]}\n"
            "修正后请明确说明：1) 针对哪些反馈做了哪些修改；2) 修改后的模型与上一版的差异。"
        )
        _pub_event(
            task_id,
            "node_progress",
            "modeling_agent",
            {"stage": "revise_with_feedback", "feedback_length": len(str(feedback)[:2000])},
        )

    # 流式输出：逐 chunk 推 node_delta 事件（前端像 chat 一样逐字渲染）
    model_output, usage = invoke_streaming_with_retry(
        llm,
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ],
        task_id=task_id,
        node="modeling_agent",
    )
    _log_usage(task_id, "modeling", usage)

    _pub_event(
        task_id,
        "node_end",
        "modeling_agent",
        {
            "step": idx + 1,
            "output_length": len(model_output),
            "summary": model_output[:800],
            "title": "模型构建",
            "desc": f"建立数学模型，输出 {len(model_output)} 字",
        },
    )

    if state["mode"] == "execute":
        _save_working_memory(task_id, "modeling", model_output)

    return {
        "model_output": model_output,
        "current_step_index": idx,
        # 消费回退标志：本次回退已在建模节点执行，后续走正常下一步（solving→verification）
        "rollback_target": None,
        "messages": [
            SystemMessage(content=f"[建模Agent] 第{idx + 1}步完成，输出 {len(model_output)} 字")
        ],
    }


