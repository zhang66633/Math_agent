"""Verification agent node - model checking, sensitivity analysis, rollback flag.

Split from core/nodes.py: nodes.py keeps only orchestration nodes
(classify/retrieve/plan/format_response) plus re-exports.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.state import AgentState
from app.sandbox.executor import SandboxExecutor

from ..llm.factory import get_llm
from ..node_helpers import (
    _check_cancelled,
    _clip_head_tail,
    _extract_code_block,
    _extract_verdict_json,
    _log_usage,
    _next_step,
    _pub_event,
    _save_working_memory,
    build_verification_feedback,
    invoke_streaming_with_retry,
)
from ..prompts.verification import (
    VERIFICATION_SYSTEM_PROMPT,
    VERIFICATION_TEACH_SYSTEM_PROMPT,
    VERIFICATION_TEACH_USER_TEMPLATE,
    VERIFICATION_USER_TEMPLATE,
)


def verification_agent_node(state: AgentState) -> dict:
    """验证分析 Agent — 检验模型+结果，判定通过或回退。"""
    idx = _next_step(state)
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "verification_agent", {"step": idx + 1})
    llm = get_llm("verification", state.get("api_key_config"))

    if state["mode"] == "teach":
        system_prompt = VERIFICATION_TEACH_SYSTEM_PROMPT
        user_prompt = VERIFICATION_TEACH_USER_TEMPLATE.format(
            problem=state["problem_raw"],
            analysis=_clip_head_tail(state.get("analysis_output", "无"), 2000),
            model=_clip_head_tail(state.get("model_output", "无"), 2000),
            solving=_clip_head_tail(state.get("solving_output", "无"), 2000),
        )
    else:
        system_prompt = VERIFICATION_SYSTEM_PROMPT
        # 头尾截断而非只砍头（审查 C4）：求解报告的数值结论与检验段
        # 大多在文末，旧实现 [:2000] 让验证官只看残卷就下 PASS/FAIL 判定
        user_prompt = VERIFICATION_USER_TEMPLATE.format(
            problem=state["problem_raw"],
            analysis=_clip_head_tail(state.get("analysis_output", "无"), 2500),
            model=_clip_head_tail(state.get("model_output", "无"), 3500),
            solving=_clip_head_tail(state.get("solving_output", "无"), 4500),
        )

    # 流式输出：逐 chunk 推 node_delta 事件（前端像 chat 一样逐字渲染）
    full_text, usage = invoke_streaming_with_retry(
        llm,
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
        task_id=task_id,
        node="verification_agent",
    )
    _log_usage(task_id, "verification", usage)

    # 提取 JSON 判定块（_extract_verdict_json：兼容嵌套/围栏/前后散文，替换旧正则）
    ver_json = _extract_verdict_json(full_text)

    passed = ver_json.get("verdict", "PASS") == "PASS"
    # 回退目标：仅 FAIL 时读取判定块；白名单仅 modeling/solving（两者都会消费回退标志），
    # 其余值（LLM 幻觉）回退到 modeling，PASS 永不回退
    rollback = None
    if not passed:
        raw_target = ver_json.get("rollback_target")
        rollback = raw_target if raw_target in ("modeling", "solving") else "modeling"

    # ── 回退控制：rollback_target 非空即「待回退」，由 modeling 节点消费，
    #    避免验证 FAIL 后反复被路由回 modeling 造成死循环 ──
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    plan = state.get("execution_plan", [])

    if passed:
        # PASS 绝不触发回退，步骤指针保持当前位置
        rollback_target = None
        new_retry_count = retry_count
        next_step_index = idx
    else:
        new_retry_count = retry_count + 1
        if new_retry_count <= max_retries:
            # 仍有重试额度：回退到 modeling，并把指针拨回其前一位，
            # 让正常下一步自然重跑 modeling→solving→verification
            rollback_target = rollback
            if rollback_target in plan:
                next_step_index = plan.index(rollback_target) - 1
            else:
                next_step_index = idx
        else:
            # 重试额度耗尽：放弃回退，继续后续流程（写作→format_response）
            rollback_target = None
            next_step_index = idx

    # 如果有代码块，尝试执行灵敏度分析
    code = _extract_code_block(full_text)
    if code and passed:
        try:
            sandbox = SandboxExecutor()
            exec_result = sandbox.run(code)
            if exec_result["success"]:
                full_text += (
                    f"\n\n### 灵敏度分析执行结果\n```\n{exec_result['stdout'][:2000]}\n```\n"
                )
        except Exception:
            pass

    _pub_event(
        task_id,
        "node_end",
        "verification_agent",
        {
            "step": idx + 1,
            "passed": passed,
            "rollback_target": rollback_target,
            "summary": full_text[:800],
            "title": "验证分析",
            "desc": (
                "✅ 通过"
                if passed
                else (
                    "❌ 不通过，回退到 " + rollback if rollback_target else "❌ 不通过，重试已耗尽"
                )
            ),
            "output_length": len(full_text),
        },
    )

    if state["mode"] == "execute":
        _save_working_memory(task_id, "verification", full_text, extra={"passed": passed})

    return {
        "verification_passed": passed,
        "verification_output": full_text,
        # 修正反馈取判定 JSON 的问题清单而非正文前 500 字（审查 C3：
        # JSON 判定块在末尾，砍头正好切掉 critical_issues）
        "verification_feedback": (
            build_verification_feedback(full_text, ver_json) if not passed else None
        ),
        "rollback_target": rollback_target,
        "retry_count": new_retry_count,
        "current_step_index": next_step_index,
        "messages": [
            SystemMessage(
                content=f"[验证Agent] 第{idx + 1}步完成 — "
                f"{'✅ 通过' if passed else ('❌ 不通过，回退到 ' + rollback_target if rollback_target else '❌ 不通过，重试已耗尽')}"
            )
        ],
    }
