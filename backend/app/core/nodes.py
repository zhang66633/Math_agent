"""Graph node entry - orchestration nodes (classify / retrieve / plan / format_response).

The 7 agent node implementations live in core/agents/<agent>.py; this module
keeps orchestration nodes and re-exports agent nodes (import-path compatible).
"""


import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.core.state import AgentState
from app.knowledge.loader import KnowledgeBaseLoader

from .llm.factory import get_llm
from .node_helpers import (  # noqa: F401  (god-files 拆分 #31：辅助函数外置)
    TaskCancelledError,
    _check_cancelled,
    _clean_md,
    _clip_head_tail,
    _collect_file_urls,
    _collect_image_urls,
    _extract_code_block,
    _extract_json,
    _extract_verdict_json,
    _is_cancelled,
    _log_usage,
    _next_step,
    _persist_task_files,
    _persist_task_images,
    _pub_event,
    _save_working_memory,
    build_verification_feedback,
    get_cancel_event,
    invoke_streaming_with_retry,
    invoke_with_retry,
    logger,
    parse_code_result,
    parse_execution_plan,
    tool_call_id,
    tool_timeout,
)
from .prompts.classifier import CLASSIFIER_SYSTEM_PROMPT, CLASSIFIER_USER_TEMPLATE
from .prompts.planner import PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE


def classify_problem(state: AgentState) -> dict:
    """识别问题类型、复杂度、数据依赖。"""
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "classify")

    llm = get_llm("classifier", state.get("api_key_config"))
    prompt = CLASSIFIER_USER_TEMPLATE.format(problem=state["problem_raw"])

    response = llm.invoke(
        [
            SystemMessage(content=CLASSIFIER_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
    )
    _log_usage(task_id, "classify", response)

    # 解析 JSON 输出
    result = _extract_json(str(response.content))

    # 枚举白名单校验（审查 P1）：解析失败返回 {} 或 LLM 给出中文等非法值时，
    # 原实现静默放行 → 标签检索整体跳过、planner 拿到空类型。
    # 非法值降级为安全默认；不重试（分类成本低、下游有兜底）。
    _VALID_TYPES = {
        "optimization", "prediction", "evaluation", "classification", "fitting",
        "graph_theory", "game_theory", "queueing", "differential_equation", "composite",
    }
    _VALID_COMPLEXITY = {"simple", "composite", "innovative"}
    _VALID_DEP = {"theoretical", "given_data", "self_collect"}
    _ptype = str(result.get("problem_type", "")).strip().lower()
    if _ptype not in _VALID_TYPES:
        _ptype = "composite"  # 综合类最安全：检索与规划都不会走进死胡同
    _cx = str(result.get("problem_complexity", "")).strip().lower()
    if _cx not in _VALID_COMPLEXITY:
        _cx = "simple"
    _dep = str(result.get("data_dependency", "")).strip().lower()
    if _dep not in _VALID_DEP:
        _dep = "theoretical"
    result["problem_type"] = _ptype
    result["problem_complexity"] = _cx
    result["data_dependency"] = _dep

    _pub_event(
        task_id,
        "node_end",
        "classify",
        {
            "problem_type": result.get("problem_type", ""),
            "problem_complexity": result.get("problem_complexity", "simple"),
            "summary": result.get("summary", "") or json.dumps(result, ensure_ascii=False),
            "output_length": len(json.dumps(result, ensure_ascii=False)),
            "title": "问题分类",
            "desc": result.get("problem_type", "")
            + " · "
            + result.get("problem_complexity", "simple"),
        },
    )

    # 工作记忆：保存分类结果
    _save_working_memory(
        task_id,
        "classify",
        json.dumps(result, ensure_ascii=False),
        extra={
            "problem_type": result.get("problem_type", ""),
            "complexity": result.get("problem_complexity", "simple"),
        },
    )

    return {
        "problem_type": result.get("problem_type", ""),
        "problem_complexity": result.get("problem_complexity", "simple"),
        "data_dependency": result.get("data_dependency", "theoretical"),
        "messages": [
            SystemMessage(
                content=f"分类结果: 类型={result.get('problem_type')}, "
                f"复杂度={result.get('problem_complexity')}, "
                f"摘要={result.get('summary', '')}"
            )
        ],
    }


# ============================================================
# 节点 2: 知识库检索
# ============================================================
def retrieve_knowledge(state: AgentState) -> dict:
    """从三层知识库检索相关内容。"""
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "retrieve_knowledge")
    settings = get_settings()

    loader = KnowledgeBaseLoader(settings.kb_root)

    methods: list[dict] = []
    papers: list[dict] = []
    templates: list[dict] = []
    problems: list[dict] = []

    problem_type = state["problem_type"]
    # 审查 P1：真题附件挂载门槛——仅当分类器判定本题依赖给定数据时才允许
    data_dependency = str(state.get("data_dependency") or "theoretical")

    if problem_type:
        # 标签过滤 — 精确匹配
        for card in loader.get_methods_by_category(problem_type):
            methods.append(
                {
                    "id": card.id,
                    "name": card.name,
                    "principle": card.principle[:300],
                    "category": card.category,
                    "page_content": card.principle[:500],
                }
            )

        for paper in loader.get_papers_by_type(problem_type):
            # Build rich page_content for downstream agents
            pc = f"{paper.title} [{paper.year} {paper.competition} {paper.problem_id}] {paper.model.approach[:200]}"
            papers.append(
                {
                    "id": paper.id,
                    "title": paper.title,
                    "year": paper.year,
                    "competition": paper.competition,
                    "problem_id": paper.problem_id,
                    "approach": paper.model.approach,
                    "page_content": pc[:500],
                }
            )

        for tpl in loader.get_templates_for_type(problem_type):
            templates.append(
                {
                    "id": tpl.id,
                    "name": tpl.name,
                    "applicable_to": tpl.applicable_to,
                    "page_content": tpl.name,
                }
            )

        for prob in loader.get_problems_by_type(problem_type):
            # 审查 P1：只有用户题本身依赖给定数据时，历史真题的附件才有被
            # 挂载的意义；其余情况仅作参考信息，剥离附件防误挂
            prob_data_files = prob.data_files if data_dependency == "given_data" else []
            pc = f"{prob.title} [{prob.year} {prob.competition} {prob.problem_id}] {prob.background[:300]}"
            problems.append(
                {
                    "id": prob.id,
                    "title": prob.title,
                    "year": prob.year,
                    "competition": prob.competition,
                    "problem_id": prob.problem_id,
                    "background": prob.background[:300],
                    "objectives": prob.objectives,
                    "data_description": prob.data_description,
                    "data_files": prob_data_files,
                    "page_content": pc[:500],
                }
            )

    # 语义搜索 — 始终执行，与 tag 结果互补
    tag_ids = (
        {m.get("id") for m in methods}
        | {p.get("id") for p in papers}
        | {t.get("id") for t in templates}
        | {pr.get("id") for pr in problems}
    )
    try:
        from ..knowledge.retriever import get_shared_retriever

        retriever = get_shared_retriever()
        docs = retriever.invoke(state["problem_raw"], k=5)
        for doc in docs:
            meta = doc.metadata
            doc_id = meta.get("id", "")
            if doc_id in tag_ids:
                continue  # 跳过 tag 已有结果
            if meta.get("type") == "method_card":
                methods.append(
                    {
                        "id": meta.get("id"),
                        "name": meta.get("name", ""),
                        "principle": "",
                        "category": [],
                        "page_content": doc.page_content[:500],
                    }
                )
            elif meta.get("type") == "paper":
                papers.append(
                    {
                        "id": meta.get("id"),
                        "title": meta.get("title", ""),
                        "year": meta.get("year"),
                        "competition": meta.get("competition"),
                        "problem_id": meta.get("problem_id", ""),
                        "approach": "",
                        "page_content": doc.page_content[:500],
                    }
                )
            elif meta.get("type") == "template":
                templates.append(
                    {
                        "id": meta.get("id"),
                        "name": meta.get("name", ""),
                        "applicable_to": [],
                        "page_content": doc.page_content[:500],
                    }
                )
            elif meta.get("type") == "problem":
                # 审查 P1：语义近邻≠题目相关。语义路径命中的历史真题一律
                # 不携带 data_files——否则自定义题会误挂别人的数据集进沙箱。
                # （data_files 仅保留在下方 tag 精确匹配且 data_dependency==given_data 的路径）
                problems.append(
                    {
                        "id": meta.get("id"),
                        "title": meta.get("title", ""),
                        "year": meta.get("year"),
                        "competition": meta.get("competition"),
                        "problem_id": meta.get("problem_id", ""),
                        "background": "",
                        "objectives": [],
                        "data_description": meta.get("data_description", ""),
                        "data_files": [],
                        "page_content": doc.page_content[:500],
                    }
                )
    except Exception as e:
        # 向量库未初始化时优雅降级（tag 结果仍可用）；但不静默——
        # 否则「知识库没检索到内容」与「向量检索坏了」在现象上无法区分
        logger.warning("语义检索失败，仅使用 tag 精确匹配结果: %s", e)

    _pub_event(
        task_id,
        "node_end",
        "retrieve_knowledge",
        {
            "methods_count": len(methods),
            "papers_count": len(papers),
            "templates_count": len(templates),
            "problems_count": len(problems),
            "summary": f"检索到 {len(methods)} 个方法, {len(papers)} 篇论文, {len(templates)} 个模板, {len(problems)} 道真题",
            "title": "知识检索",
            "desc": f"方法 {len(methods)} · 论文 {len(papers)} · 模板 {len(templates)} · 真题 {len(problems)}",
            "output_length": len(methods) + len(papers) + len(templates) + len(problems),
        },
    )

    # 工作记忆：保存检索结果摘要
    _save_working_memory(
        task_id,
        "retrieve",
        json.dumps(
            {
                "methods_count": len(methods),
                "papers_count": len(papers),
                "templates_count": len(templates),
            },
            ensure_ascii=False,
        ),
    )

    # ── 数据文件发现：找到匹配问题对应的本地数据文件目录 ──
    data_files_list: list[dict] = []
    data_files_dir = ""
    for p in problems:
        files = p.get("data_files") or []
        if files:
            data_files_list.extend(files)
            # 尝试在 data/problems/ 下查找对应目录
            year = p.get("year")
            pid = p.get("problem_id")
            if year and pid:
                candidate = settings.project_root / "data" / "problems" / f"{year}{pid}"
                if candidate.exists():
                    data_files_dir = str(candidate.resolve())
                    break

    return {
        "kb_methods": methods,
        "kb_papers": papers,
        "kb_templates": templates,
        "kb_problems": problems,
        "data_files": data_files_list,
        "data_files_dir": data_files_dir,
        "messages": [
            SystemMessage(
                content=f"知识库检索: 找到 {len(methods)} 个方法, "
                f"{len(papers)} 篇论文, {len(templates)} 个模板, "
                f"{len(problems)} 道竞赛真题"
                + (f", 数据文件 {len(data_files_list)} 个" if data_files_list else "")
            )
        ],
    }


# ============================================================
# 节点 3: 执行规划
# ============================================================
def plan_execution(state: AgentState) -> dict:
    """根据分类和知识库，动态生成子 agent 执行计划。"""
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "plan_execution")
    llm = get_llm("planner", state.get("api_key_config"))

    # 情景记忆：召回历史相似题的经验
    experiences_str = "（无历史经验）"
    if state["mode"] == "execute":
        try:
            from app.services.episodic_memory import EpisodicMemory

            em = EpisodicMemory()
            exps = em.recall(
                query=state["problem_raw"],
                problem_type=state.get("problem_type", ""),
                k=3,
            )
            if exps:
                experiences_str = "\n".join(f"- {e}" for e in exps)
        except Exception:
            pass

    # 构建知识库上下文
    methods_str = (
        "\n".join(f"- {m['name']}: {m.get('principle', '')[:100]}" for m in state["kb_methods"])
        or "（无推荐的特定方法）"
    )

    templates_str = "\n".join(f"- {t['name']}" for t in state["kb_templates"]) or "（无匹配模板）"

    papers_str = (
        "\n".join(f"- [{p['year']}] {p['title']}" for p in state["kb_papers"]) or "（无参考论文）"
    )

    problems_str = (
        "\n".join(
            f"- [{p.get('year', '?')} {p.get('competition', '?')} {p.get('problem_id', '?')}] "
            f"{p.get('title', '?')}"
            for p in state["kb_problems"]
        )
        or "（无相关竞赛真题）"
    )

    system_prompt = PLANNER_SYSTEM_PROMPT.format(
        methods=methods_str,
        templates=templates_str,
        papers=papers_str,
        problems=problems_str,
        experiences=experiences_str,
    )

    user_prompt = PLANNER_USER_TEMPLATE.format(
        problem=state["problem_raw"],
        problem_type=state["problem_type"],
        complexity=state["problem_complexity"],
        data_dependency=state["data_dependency"],
    )

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    _log_usage(task_id, "plan", response)

    plan = _extract_json(str(response.content))

    # 白名单过滤 + 理由提取（v2.2：planner 输出 [{step, reason}]，
    # 时间线按真实理由展示"方案思考"，而非写死的通用描述——审查 C1）
    execution_plan, plan_reasons = parse_execution_plan(plan)

    # 协议 v2.1：推送动态执行计划（前端按真实计划渲染时间线，而非写死步骤）；
    # v2.2 附 reasons：每个步骤为什么出现在这道题的计划里
    _pub_event(
        task_id,
        "plan",
        "plan_execution",
        {
            "plan": execution_plan,
            "step_count": len(execution_plan),
            "reasons": plan_reasons,
        },
    )

    return {
        "execution_plan": execution_plan,
        "current_step_index": -1,
        "messages": [
            SystemMessage(
                content=(
                    f"执行计划: {' → '.join(execution_plan)}"
                    + (
                        "\n计划理由: "
                        + "；".join(
                            f"{k}（{v}）" for k, v in plan_reasons.items() if k in execution_plan
                        )
                        if plan_reasons
                        else ""
                    )
                )
            )
        ],
    }


# ============================================================
# Agent 节点 — 每个 agent 节点递增 current_step_index
# ============================================================
def format_response(state: AgentState) -> dict:
    """整合所有 agent 输出，按模式格式化。"""
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "format_response")

    if state["mode"] == "teach":
        final = _format_teach_response(state)
    else:
        final = _format_execute_response(state)

    _pub_event(
        task_id,
        "node_end",
        "format_response",
        {
            "mode": state["mode"],
            "output_length": len(final),
        },
    )

    return {
        "final_response": final,
        "messages": [SystemMessage(content="编排完成，最终结果已生成。")],
    }


def _format_execute_response(state: AgentState) -> str:
    """方案输出模式: 以写作Agent的完整论文为最终输出。

    各阶段中间产出（analysis/model/solving/verification）已通过
    node_end 进度事件展示给用户，不再重复拼进最终论文，
    否则会出现"假设写两遍、约束写两遍"的内容重复。
    """
    writing = state.get("writing_output")
    if writing:
        return writing

    # 兜底：写作节点未产出时，退化为拼接中间结果
    parts = []
    if state.get("analysis_output"):
        parts.append(state["analysis_output"])
    if state.get("model_output"):
        parts.append(state["model_output"])
    if state.get("solving_output"):
        parts.append(state["solving_output"])
    if state.get("verification_output"):
        parts.append(state["verification_output"])
    return "\n\n---\n\n".join(parts) if parts else "（无输出）"


def _format_teach_response(state: AgentState) -> str:
    """教学模式: 整合为苏格拉底式引导对话。"""
    parts = ["## 🎓 教学模式 — 引导式分析\n"]

    if state.get("analysis_output"):
        parts.append("### 💡 问题思考引导\n")
        parts.append(state["analysis_output"])
        parts.append("")

    if state.get("model_output"):
        parts.append("### 🧩 模型思路启发\n")
        parts.append(state["model_output"])
        parts.append("")

    if state.get("solving_output"):
        parts.append("### 🔧 求解方向提示\n")
        parts.append(state["solving_output"])
        parts.append("")

    if state.get("verification_output"):
        parts.append("### ✅ 自检清单\n")
        parts.append(state["verification_output"])
        parts.append("")

    if state.get("writing_output"):
        parts.append("### 📝 框架建议\n")
        parts.append(state["writing_output"])
        parts.append("")

    if len(parts) <= 1:
        return "（教学模式 — 引导式对话待实现）"

    return "\n".join(parts)


# ============================================================
# 工具函数
# ============================================================


# --- agent node re-exports (implementations moved to core/agents/) ---
# workflow.py / tests / scripts still import these names from app.core.nodes.
from .agents.analysis import analysis_agent_node
from .agents.data_preprocessing import data_preprocessing_agent_node
from .agents.export_results import export_results_agent_node
from .agents.modeling import modeling_agent_node
from .agents.solving import solving_agent_node
from .agents.verification import verification_agent_node
from .agents.writing import build_paper_sections, writing_agent_node

__all__ = [
    "analysis_agent_node",
    "build_paper_sections",
    "classify_problem",
    "data_preprocessing_agent_node",
    "export_results_agent_node",
    "format_response",
    "modeling_agent_node",
    "plan_execution",
    "retrieve_knowledge",
    "solving_agent_node",
    "verification_agent_node",
    "writing_agent_node",
]
