"""主编排工作流 — 构建 LangGraph StateGraph。

拓扑结构:
    START
      │
      ▼
    classify_problem   (LLM: 识别问题类型)
      │
      ▼
    retrieve_knowledge (无LLM: 混合检索)
      │
      ▼
    plan_execution     (LLM: 生成执行计划)
      │
      ▼
    route_to_first_agent (条件边)
      │
      ├── analysis_agent ──────┐
      ├── modeling_agent ──────┤
      ├── solving_agent ───────┤── after_agent_router (条件边)
      ├── verification_agent ──┤       │
      ├── writing_agent ───────┘       │
      │                                 │
      └── format_response ←────────────┘
               │
               ▼
              END
"""

from langgraph.graph import END, START, StateGraph

from .nodes import (
    analysis_agent_node,
    classify_problem,
    data_preprocessing_agent_node,
    export_results_agent_node,
    format_response,
    modeling_agent_node,
    plan_execution,
    retrieve_knowledge,
    solving_agent_node,
    verification_agent_node,
    writing_agent_node,
)
from .router import AGENT_NODES, after_agent_router, route_to_first_agent
from .state import AgentState

# 节点函数注册表：节点名 → 函数（与 AGENT_NODES 的节点名一一对应）
_AGENT_NODE_FNS = {
    "analysis_agent": analysis_agent_node,
    "modeling_agent": modeling_agent_node,
    "data_preprocessing_agent": data_preprocessing_agent_node,
    "solving_agent": solving_agent_node,
    "verification_agent": verification_agent_node,
    "export_results_agent": export_results_agent_node,
    "writing_agent": writing_agent_node,
}


def build_orchestrator() -> StateGraph:
    """构建并编译主编排图。"""

    workflow = StateGraph(AgentState)

    # ---- 编排节点 ----
    workflow.add_node("classify_problem", classify_problem)
    workflow.add_node("retrieve_knowledge", retrieve_knowledge)
    workflow.add_node("plan_execution", plan_execution)

    # ---- Agent 节点（按 AGENT_NODES 单一真源注册）----
    for node_name, fn in _AGENT_NODE_FNS.items():
        workflow.add_node(node_name, fn)

    # ---- 格式化输出 ----
    workflow.add_node("format_response", format_response)

    # ---- 固定边（编排流水线）----
    workflow.add_edge(START, "classify_problem")
    workflow.add_edge("classify_problem", "retrieve_knowledge")
    workflow.add_edge("retrieve_knowledge", "plan_execution")

    # ---- 动态路由：planner → 第一个 agent ----
    # 条件边映射同样从 AGENT_NODES 派生（目标含 format_response）
    _route_map = {node: node for node in AGENT_NODES.values()}
    _route_map["format_response"] = "format_response"
    workflow.add_conditional_edges(
        "plan_execution",
        route_to_first_agent,
        _route_map,
    )

    # ---- 动态路由：每个 agent 完成后 → 下一步 ----
    for node_name in AGENT_NODES.values():
        workflow.add_conditional_edges(
            node_name,
            after_agent_router,
            _route_map,
        )

    # ---- 格式化后结束 ----
    workflow.add_edge("format_response", END)

    # 编译图
    return workflow.compile()


# 全局单例
_orchestrator = None


def get_orchestrator():
    """获取主编排器单例。"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()
    return _orchestrator
