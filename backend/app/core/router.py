"""动态路由逻辑 - plan_execution → first_agent, agent → next_agent/format_response."""

from .state import AgentState

# ── plan 步骤名 → 图节点名（单一真源）────────────────────────────────
# workflow.py 的节点注册与条件边映射、route_to_first_agent、
# after_agent_router 共用这一张表——加/改 agent 只改这一处，
# 不再有三份手抄 node_map 各自漂移的风险。
AGENT_NODES: dict[str, str] = {
    "analysis": "analysis_agent",
    "modeling": "modeling_agent",
    "data_preprocessing": "data_preprocessing_agent",
    "solving": "solving_agent",
    "verification": "verification_agent",
    "export_results": "export_results_agent",
    "writing": "writing_agent",
}


def route_to_first_agent(state: AgentState) -> str:
    """根据执行计划，路由到第一个 agent 节点。

    如果计划为空或所有步骤完成，直接跳到 format_response。
    """
    plan = state.get("execution_plan", [])
    if not plan:
        return "format_response"

    first_step = plan[0]
    return AGENT_NODES.get(first_step, "analysis_agent")


def after_agent_router(state: AgentState) -> str:
    """每个 agent 执行完后，路由到下一个 agent 或 format_response。

    仅当存在「待回退」目标（rollback_target 非空）且仍有重试额度时回退一次；
    建模节点会消费该标志，从而避免验证 FAIL 反复回退到 modeling 的死循环。
    """
    plan = state.get("execution_plan", [])
    current_idx = state.get("current_step_index", 0)
    max_retries = state.get("max_retries", 3)
    retry_count = state.get("retry_count", 0)

    # 回退：rollback_target 非空即存在待处理回退，且未超重试限制时才路由一次
    rollback_target = state.get("rollback_target")
    if rollback_target and retry_count <= max_retries:
        return AGENT_NODES.get(rollback_target, "modeling_agent")

    # 正常流程：检查下一个步骤
    next_idx = current_idx + 1
    if next_idx >= len(plan):
        return "format_response"

    next_step = plan[next_idx]
    return AGENT_NODES.get(next_step, "format_response")
