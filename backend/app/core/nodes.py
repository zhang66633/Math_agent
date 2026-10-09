"""图节点函数 — classify / retrieve / plan / agent / format。"""

import json
import re
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.config import get_settings
from app.core.state import AgentState
from app.knowledge.loader import KnowledgeBaseLoader
from app.sandbox.executor import SandboxExecutor
from app.tools.interaction_tools import RunCodeTool
from app.tools.kb_tools import create_kb_tools
from app.tools.math_tools import create_math_tools
from app.tools.web_search_tools import create_web_search_tools

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
from .prompts.analysis import (
    ANALYSIS_SYSTEM_PROMPT,
    ANALYSIS_TEACH_SYSTEM_PROMPT,
    ANALYSIS_TEACH_USER_TEMPLATE,
    ANALYSIS_USER_TEMPLATE,
)
from .prompts.classifier import CLASSIFIER_SYSTEM_PROMPT, CLASSIFIER_USER_TEMPLATE
from .prompts.modeling import (
    MODELING_SYSTEM_PROMPT,
    MODELING_TEACH_SYSTEM_PROMPT,
    MODELING_TEACH_USER_TEMPLATE,
    MODELING_USER_TEMPLATE,
)
from .prompts.planner import PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE
from .prompts.preprocessing import (
    PREPROCESSING_SYSTEM_PROMPT,
    PREPROCESSING_USER_TEMPLATE,
)
from .prompts.solving import (
    SOLVING_TEACH_SYSTEM_PROMPT,
    SOLVING_TEACH_USER_TEMPLATE,
    SOLVING_TOOL_SYSTEM_PROMPT,
    SOLVING_TOOL_USER_TEMPLATE,
)
from .prompts.verification import (
    VERIFICATION_SYSTEM_PROMPT,
    VERIFICATION_TEACH_SYSTEM_PROMPT,
    VERIFICATION_TEACH_USER_TEMPLATE,
    VERIFICATION_USER_TEMPLATE,
)
from .prompts.writing import (
    RED_TEAM_PROMPT,
    WRITING_ABSTRACT_PROMPT,
    WRITING_OUTLINE_PROMPT,
    WRITING_REVISE_PROMPT,
    WRITING_SECTION_PROMPT,
    WRITING_TEACH_SYSTEM_PROMPT,
    WRITING_TEACH_USER_TEMPLATE,
)


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


def solving_agent_node(state: AgentState) -> dict:
    """求解计算 Agent。

    - teach 模式：引导式教学（不执行代码）。
    - execute 模式：多轮 tool loop —— 通过 bind_tools 动态调用
      run_code / sympy / 优化 / 知识库 / 搜索，形成"求解→检验→灵敏度"闭环，
      产出证据驱动的结构化求解报告。
    """
    idx = _next_step(state)
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "solving_agent", {"step": idx + 1})
    llm = get_llm("solving", state.get("api_key_config"))

    model_text = state.get("model_output") or "无模型"

    # ── teach 模式：保持原有引导式输出（流式）──
    if state["mode"] == "teach":
        system_prompt = SOLVING_TEACH_SYSTEM_PROMPT.format(model_info=model_text[:3000])
        user_prompt = SOLVING_TEACH_USER_TEMPLATE.format(
            problem=state["problem_raw"],
            model=model_text[:3000],
        )
        final_output, usage = invoke_streaming_with_retry(
            llm,
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ],
            task_id=task_id,
            node="solving_agent",
        )
        _log_usage(task_id, "solving_teach", usage)
        _pub_event(
            task_id,
            "node_end",
            "solving_agent",
            {
                "step": idx + 1,
                "output_length": len(final_output),
                "images_count": 0,
                "summary": final_output[:800],
                "title": "求解计算",
                "desc": f"输出 {len(final_output)} 字（教学模式）",
            },
        )
        return {
            "solving_output": final_output,
            "current_step_index": idx,
            # 消费回退标志（求解回退目标）：防止路由再次回到 solving 自循环
            "rollback_target": None,
            "messages": [SystemMessage(content=f"[求解Agent] 第{idx + 1}步完成（教学模式）")],
        }

    # ── execute 模式：多轮 tool loop ──
    # 注入数据文件目录到 RunCodeTool
    run_code_tool = RunCodeTool()
    run_code_tool.data_files_dir = state.get("data_files_dir", "")

    tools = [run_code_tool] + create_math_tools() + create_kb_tools() + create_web_search_tools()
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    # 构建数据文件上下文（注入系统 prompt 的 {data_files_section} 占位符；
    # 无文件时也要明确告知，防止模型臆造不存在的文件名——审查 P0-1 修复）
    data_files_list = state.get("data_files") or []
    if data_files_list:
        _lines = ["题目数据文件已挂载到沙箱工作目录，**直接用文件名读取，不要传 file_ids**："]
        for df in data_files_list:
            _lines.append(
                f"- `{df.get('filename', '?')}`: "
                f"{df.get('rows', '?')}行, "
                f"列: {', '.join(df.get('columns', []))}"
            )
        _lines.append(
            "用 pd.read_csv / pd.read_excel / pd.read_parquet 按扩展名选择读取方式；"
            "大文件优先采样或聚合后再分析。"
        )
        data_files_section = "\n".join(_lines)
    else:
        data_files_section = (
            "本题**没有预挂载的数据文件**。如需数据支撑，请依据题目描述构造合理的模拟/示例数据，"
            "并在报告中明确说明数据来源与构造假设；禁止尝试读取任何未列出的文件。"
        )

    system_prompt = SOLVING_TOOL_SYSTEM_PROMPT.format(
        model_info=model_text,
        data_files_section=data_files_section,
        # 时间预算如实告知（审查 P0-3）：模型按真实预算规划拆分，
        # 而不是撞了超时才盲目重试同样的大计算
        time_budget_section=(
            f"- 单次 run_code 执行预算约 {get_settings().sandbox_timeout} 秒，"
            "超时会被强制终止（只能拿到终止前的部分输出）。\n"
            "- 预计超过预算的计算必须拆分：先小规模/小迭代跑通验证正确性，"
            "再分步放大规模；严禁单次调用塞入全量重计算。"
        ),
    )
    # EDA 结论注入求解侧（审查 P1：preprocessed_data 曾是悬空字段，EDA 结论被丢弃）
    _eda = (state.get("preprocessed_data") or "").strip()
    eda_block = f"\n## 数据预处理结论（EDA）\n{_eda[:3000]}\n" if _eda else ""
    user_prompt = SOLVING_TOOL_USER_TEMPLATE.format(
        problem=state["problem_raw"],
        model=model_text,
        eda_block=eda_block,
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    all_images: list[str] = []
    all_xlsx: list[str] = []
    all_csv: list[str] = []
    all_html: list[str] = []
    max_rounds = 10  # 工具调用轮数上限（每轮可并发多个工具）

    # 工具结果截断目录（借鉴 cc-haha maxResultSizeChars）
    # 注意：不使用局部 from ..config import get_settings —— 会遮蔽模块级导入，
    # 令上文 time_budget_section f-string 里的 get_settings() 触发 F823（未赋值即引用）
    _settings = get_settings()
    _persist_dir = _settings.project_root / "data" / "task_files" / task_id
    _persist_dir.mkdir(parents=True, exist_ok=True)

    MAX_TOOL_RESULT_CHARS = 12000

    def _truncate_tool_result(result_text: str, tool_name: str) -> str:
        """截断超长工具结果，完整内容写入磁盘（借鉴 cc-haha）。

        错误段保护：interaction_tools 把「错误：…」拼在结果末尾，
        头部截断会把错误整体切掉——LLM 看到失败却看不到原因（审查 P1）。
        截断后无条件回追错误段。
        """
        if len(result_text) <= MAX_TOOL_RESULT_CHARS:
            return result_text
        import uuid as _uuid

        persist_path = _persist_dir / f"_tool_{tool_name}_{_uuid.uuid4().hex[:8]}.txt"
        try:
            persist_path.write_text(result_text, encoding="utf-8")
        except Exception:
            pass
        kept = result_text[:MAX_TOOL_RESULT_CHARS]
        note = (
            f"\n\n…（结果已截断，共 {len(result_text)} 字符。完整结果已保存至 {persist_path}）"
        )
        # 回追错误段（截断点之后的所有以「错误」开头的行及其后续缩进行）
        err_lines: list[str] = []
        for ln in result_text[MAX_TOOL_RESULT_CHARS:].splitlines():
            if ln.lstrip().startswith(("错误", "error", "Error", "ERROR")) or (
                err_lines and (ln.startswith((" ", "\t")) )
            ):
                err_lines.append(ln)
        if err_lines:
            kept = kept.rstrip() + "\n\n" + "\n".join(err_lines[-30:])
        return kept + note

    for _ in range(max_rounds):
        _check_cancelled(task_id)
        response = invoke_with_retry(llm_with_tools, messages, task_id=task_id, node="solving_tool")
        _log_usage(task_id, "solving_tool", response)
        messages.append(response)
        # 每轮 LLM 解说文本推给前端（与流式节点的 node_delta 同通道，逐轮累积）
        round_text = getattr(response, "content", "") or ""
        if round_text:
            _pub_event(task_id, "node_delta", "solving_agent", {"delta": str(round_text)})

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break  # LLM 停止调用工具 → 最后一条即结构化求解报告

        # ── 协议 v2.1：先发 tool_call（running，带 tool_call_id），
        #    执行完再发 tool_result（同一 id 回声）——前端同一卡片两段更新，内联成组 ──
        for tc in tool_calls:
            _pub_event(
                task_id,
                "tool_call",
                "solving_agent",
                {
                    "tool_call_id": tool_call_id(tc, tc.get("name")),
                    "tool_name": tc.get("name"),
                    "input": {
                        k: (str(v)[:1500] if k == "code" else v)
                        for k, v in (tc.get("args") or {}).items()
                    },
                    "status": "running",
                },
            )

        # ── 执行：run_code 串行（沙箱资源独占，注入取消事件）；
        #    其余工具线程池并行 + 每工具超时（与 chat 通道同规则）──
        def _run_one(tc: dict) -> tuple[str, dict]:
            """执行单个工具，返回 (结果文本, 元信息)。"""
            tool_name = tc.get("name")
            tool_args = tc.get("args") or {}
            tool = tool_map.get(tool_name)
            t0 = time.monotonic()
            if tool is None:
                return (
                    f"未知工具: {tool_name}",
                    {
                        "tool_name": tool_name,
                        "ok": False,
                        "error": f"未知工具: {tool_name}",
                        "duration_ms": 0,
                    },
                )
            try:
                text = tool.invoke(tool_args)
                return text, {
                    "tool_name": tool_name,
                    "ok": True,
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                }
            except Exception as e:  # noqa: BLE001
                return (
                    f"工具执行失败: {e}",
                    {
                        "tool_name": tool_name,
                        "ok": False,
                        "error": str(e)[:200],
                        "duration_ms": int((time.monotonic() - t0) * 1000),
                    },
                )

        from concurrent.futures import ThreadPoolExecutor

        results: dict[str, tuple[str, dict]] = {}

        # run_code 串行执行：任务取消 → 沙箱进程树被中断（事件级取消）
        run_code_tool.cancel_event = get_cancel_event(task_id)
        for tc in tool_calls:
            if tc.get("name") != "run_code":
                continue
            tc_id = tool_call_id(tc, "run_code")
            _pub_event(task_id, "code_exec", "solving_agent", {"status": "running", "id": tc_id})
            text, meta = _run_one(tc)
            results[tc_id] = (text, meta)
            code_data = parse_code_result(text)
            _pub_event(
                task_id,
                "code_exec",
                "solving_agent",
                {
                    "status": "done",
                    "id": tc_id,
                    **code_data,
                    "ok": meta["ok"],
                    "duration_ms": meta["duration_ms"],
                },
            )

        # 其余工具并行（每工具独立超时；超时仅放弃等待，不杀线程——与 chat 一致）
        others = [tc for tc in tool_calls if tc.get("name") != "run_code"]
        if others:
            # 不用 with：__exit__ 的 shutdown(wait=True) 会无限 join 已超时放弃的
            # 卡死线程，把整个编排器拖住（审查 P1「超时是假象」）。
            # wait=False 立即返回；cancel_futures 取消队列里尚未开跑的任务。
            _pool = ThreadPoolExecutor(max_workers=min(4, len(others)))
            try:
                _futs: dict[str, tuple] = {
                    tool_call_id(tc, tc.get("name")): (_pool.submit(_run_one, tc), tc.get("name"))
                    for tc in others
                }
                for tc_id, (_fut, tool_name) in _futs.items():
                    try:
                        text, meta = _fut.result(timeout=tool_timeout(tool_name))
                    except TimeoutError:
                        text = f"工具执行超时（{tool_timeout(tool_name):.0f}s）"
                        meta = {
                            "tool_name": tool_name,
                            "ok": False,
                            "error": text,
                            "duration_ms": int(tool_timeout(tool_name) * 1000),
                        }
                    results[tc_id] = (text, meta)
            finally:
                _pool.shutdown(wait=False, cancel_futures=True)

        # ── 结果事件回灌（按 LLM 原始顺序，id 回声）──
        for tc in tool_calls:
            tc_id = tool_call_id(tc, tc.get("name"))
            tool_name = tc.get("name")
            text, meta = results[tc_id]

            # run_code 的图/文件 URL 在结果文本末尾,截断会丢 → 先留存原行
            url_lines: list[str] = []
            if tool_name == "run_code":
                url_lines = [
                    ln for ln in text.splitlines()
                    if "/api/images/" in ln or "/api/task_files/" in ln
                ]

            # 截断超长工具结果（借鉴 cc-haha maxResultSizeChars）
            text = _truncate_tool_result(text, tool_name)

            # 截断后回补 URL 行: 求解 LLM 与事件里图链接必须完整,论文才有图
            if url_lines:
                text = f"{text.rstrip()}\n\n" + "\n".join(url_lines)

            # 收集 run_code 产出的图表和文件 URL
            if tool_name == "run_code":
                all_images.extend(_collect_image_urls(text))
                all_xlsx.extend(_collect_file_urls(text, "xlsx"))
                all_csv.extend(_collect_file_urls(text, "csv"))
                all_html.extend(_collect_file_urls(text, "html"))

            _pub_event(
                task_id,
                "tool_result",
                "solving_agent",
                {
                    "tool_call_id": tc_id,
                    "tool_name": tool_name,
                    "preview": text[:1500],
                    "ok": meta["ok"],
                    "duration_ms": meta["duration_ms"],
                    "images": _collect_image_urls(text),
                    "xlsx_files": _collect_file_urls(text, "xlsx"),
                    "csv_files": _collect_file_urls(text, "csv"),
                    "html_files": _collect_file_urls(text, "html"),
                    **({"error": meta["error"]} if meta.get("error") else {}),
                },
            )

            messages.append(
                ToolMessage(
                    content=text,
                    tool_call_id=tc_id,
                )
            )

    # 最终求解报告 = 最后一条 AI 文本消息
    final_output = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content and not (getattr(m, "tool_calls", None)):
            final_output = str(m.content)
            break

    if not final_output:
        # 兜底：轮数耗尽仍在调工具，强制让 LLM 基于已有结果总结
        fallback = llm.invoke(
            messages
            + [
                HumanMessage(
                    content="请停止调用工具，基于以上已获得的全部求解结果，立即输出结构化求解报告。"
                )
            ]
        )
        _log_usage(task_id, "solving_fallback", fallback)
        final_output = str(fallback.content)

    # 图表和文件持久化到任务文件区（临时目录可能被系统清理）
    # 先按 URL 去重（审查 B5）：多轮重试/多子问题常引用同一 run 的同一张图，
    # 不去重会虚报 images_count，也会诱导下游写作阶段多处引用同一图
    all_images = list(dict.fromkeys(all_images))
    all_xlsx = list(dict.fromkeys(all_xlsx))
    all_csv = list(dict.fromkeys(all_csv))
    all_html = list(dict.fromkeys(all_html))
    persisted = _persist_task_files(
        task_id,
        image_urls=all_images,
        xlsx_urls=all_xlsx,
        csv_urls=all_csv,
        html_urls=all_html,
    )
    # 临时 run_id URL → 持久 task_id URL 整体改写：
    # 论文/写作素材只保留永久链接，否则 24h 清理后论文图必裂（审查 P1）
    url_map: dict = persisted.get("url_map") or {}
    if url_map and final_output:
        for _old, _new in url_map.items():
            final_output = final_output.replace(_old, _new)

    _pub_event(
        task_id,
        "node_end",
        "solving_agent",
        {
            "step": idx + 1,
            "output_length": len(final_output),
            "images_count": len(all_images),
            "xlsx_count": len(all_xlsx),
            "csv_count": len(all_csv),
            "summary": final_output[:800],
            "title": "求解计算",
            "desc": f"输出 {len(final_output)} 字"
            + (f"，图表 {len(all_images)} 张" if all_images else ""),
        },
    )

    if state["mode"] == "execute":
        _save_working_memory(
            task_id, "solving", final_output, extra={"images_count": len(all_images)}
        )

    return {
        "solving_output": final_output,
        "current_step_index": idx,
        # 消费回退标志（求解回退目标）：防止路由再次回到 solving 自循环
        "rollback_target": None,
        "messages": [
            SystemMessage(
                content=f"[求解Agent] 第{idx + 1}步完成，"
                f"图表 {len(all_images)} 张，"
                f"输出 {len(final_output)} 字"
            )
        ],
    }


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


# ── 论文章节规格（方案模式分章节写作）──────────────────────────────
# 通用骨架 + 核心章「四、模型的建立与求解」按求解报告的子问题清单动态拆分。
# 铁律：禁止在此硬编码任何具体赛题的小节标题/要求——曾经的定价题专属
# 小节（品类定价/补货优化等）曾污染所有用户的论文结构（审查 P0-2）。
_GENERIC_SECTIONS: list[tuple[str, str]] = [
    (
        "一、问题重述",
        "用数学语言重述问题：明确已知量、未知量、优化/分析目标。"
        "不要照抄题目原文，要提炼出数学要素。篇幅 300-500 字。",
    ),
    (
        "二、问题分析",
        "分析问题的关键特征、难点与建模思路，2-4 段，体现'表象→机理'的递进。"
        "不要罗列假设（假设在第三章），不要堆砌空话。",
    ),
    (
        "三、模型假设与符号说明",
        "假设用有序列表，每条一句话，共 4-6 条，不给每条配冗长展开。"
        "符号说明用 Markdown 表格（符号 | 含义 | 单位）。"
        "**铁律：假设和符号全文只在此处定义一次。本章之前和之后的任何章节不得再出现假设列表或符号定义。**",
    ),
    (
        "五、模型检验与灵敏度分析",
        "独立成章。①模型正确性检验（量纲、边界、与常识对比、误差分析）"
        "②对 1-2 个关键参数做灵敏度分析，用表格呈现，给出'模型是否稳健'的结论。",
    ),
    (
        "六、模型评价与改进",
        "优点 2-3 条、不足与改进方向 2-3 条，各一句话，具体不空泛。**本章必须完整写完。**",
    ),
    (
        "参考文献",
        "用 `[1] 作者. 文献名. 来源, 年份.` 格式列 3-5 条。"
        "**只引用你确定真实存在的经典文献**（如姜启源《数学模型》、司守奎《数学建模算法与应用》等）；"
        "严禁编造。"
        "**本章必须完整写完，以最后一条文献结束。**",
    ),
    (
        "附录",
        "把材料（尤其求解结果）中出现的**全部代码块原样收录**：按模型分小节"
        "（如 `### 附录A · 问题1模型求解代码`），每节一个带语言标签的代码块"
        "（```python 等），代码一字不改、一段不少，严禁省略或改写。"
        "若材料中确实没有任何代码，写一句话说明并结束。"
        "**本章必须完整写完。**",
    ),
]

_SUBPROBLEM_RE = re.compile(r"^#{2,4}\s*子问题\s*(\d+)\s*[：:]\s*(.+?)\s*$", re.MULTILINE)


def build_paper_sections(solving_output: str) -> list[tuple[str, str]]:
    """按求解报告中的「子问题 N：标题」动态拆分核心章；解析不到时退化为单个通用核心章。"""
    matches = _SUBPROBLEM_RE.findall(solving_output or "")
    if not matches:
        return [
            *_GENERIC_SECTIONS[:3],
            (
                "四、模型的建立与求解",
                "严格按大纲完成：①建模思路 ②模型与算法（$$公式块$$、关键表格）"
                "③求解结果（引用材料中与本节直接相关的 /api/images/ 图片链接并配图注，"
                "每张图全文只引用一次，禁止跨节重复引用同一张图）④结果检验。"
                "**必须完整写完，不要截断。**",
            ),
            *_GENERIC_SECTIONS[3:],
        ]
    core: list[tuple[str, str]] = []
    for num, raw_title in matches:
        sub_title = raw_title.strip().strip("*")
        title = f"四、模型的建立与求解 — 子问题{num}"
        req = (
            f"### 子问题{num}：{sub_title}\n"
            "严格按此结构：①原理与方法 ②模型与求解（$$公式块$$、关键表格）"
            f"③求解结果（只引用求解材料中「子问题{num}」小节内出现的图片链接，"
            "配图注；**其他子问题的图留给各自小节，严禁跨节引用**——每张图全文只引用一次）"
            "④结果检验。"
            "**必须输出完整小节，不要截断。**"
        )
        core.append((title, req))
    return [*_GENERIC_SECTIONS[:3], *core, *_GENERIC_SECTIONS[3:]]


def writing_agent_node(state: AgentState) -> dict:
    """论文写作 Agent。

    - teach 模式：引导式写作教学。
    - execute 模式：分章节流水线 ——
      大纲 → 逐章生成 → 摘要(最后写,提炼真实结果) → 拼装 → 红队审校 → 最小化修订。
    """
    idx = _next_step(state)
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "writing_agent", {"step": idx + 1})
    llm = get_llm("writing", state.get("api_key_config"))

    # ── teach 模式：保持原有教学输出 ──
    if state["mode"] == "teach":
        system_prompt = WRITING_TEACH_SYSTEM_PROMPT.format(
            analysis=state.get("analysis_output", "无")[:3000],
            model=state.get("model_output", "无")[:3000],
            solving=state.get("solving_output", "无")[:3000],
            verification=state.get("verification_output", "无")[:3000],
        )
        user_prompt = WRITING_TEACH_USER_TEMPLATE.format(problem=state["problem_raw"])
        response = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        _log_usage(task_id, "writing_teach", response)
        writing_output = _clean_md(response.content)
        _pub_event(
            task_id,
            "node_end",
            "writing_agent",
            {
                "step": idx + 1,
                "output_length": len(writing_output),
            },
        )
        return {
            "writing_output": writing_output,
            "current_step_index": idx,
            "messages": [SystemMessage(content=f"[写作Agent] 第{idx + 1}步完成（教学模式）")],
        }

    # ── execute 模式：分章节流水线 ──
    # v4-pro 支持 384K 输出，给足预算
    llm_outline = llm.bind(max_tokens=8192)
    llm_section = llm.bind(max_tokens=32768)  # 普通章 32K
    llm_core_section = llm.bind(max_tokens=131072)  # 核心章 128K
    llm_abstract = llm.bind(max_tokens=8192)
    llm_redteam = llm.bind(max_tokens=8192)
    llm_revise = llm.bind(max_tokens=196608)  # 修订可能重生整篇

    materials = {
        "problem": state["problem_raw"],
        "analysis": state.get("analysis_output", "无"),
        # EDA 结论注入大纲与分章模板（审查 P1：preprocessed_data 曾是悬空字段）
        "preprocessed": (state.get("preprocessed_data") or "").strip()[:3000]
        or "（本题无数据预处理环节）",
        "model": state.get("model_output", "无"),
        "solving": state.get("solving_output", "无"),
        "verification": state.get("verification_output", "无"),
    }

    # 核心章按求解报告的子问题动态拆分（替代旧的硬编码 PAPER_SECTIONS）
    paper_sections = build_paper_sections(state.get("solving_output", ""))

    # 1) 大纲
    _pub_event(task_id, "node_progress", "writing_agent", {"stage": "outline"})
    _outline_resp = invoke_with_retry(
        llm_outline,
        [HumanMessage(content=WRITING_OUTLINE_PROMPT.format(**materials))],
        task_id=task_id,
        node="writing_outline",
    )
    _log_usage(task_id, "writing_outline", _outline_resp)
    outline = _clean_md(_outline_resp.content)

    # 提取标题（大纲首行 "# xxx"）
    paper_title = "数学建模论文"
    first_line = outline.split("\n", 1)[0].strip()
    if first_line.startswith("#"):
        paper_title = first_line.lstrip("#").strip() or paper_title

    # 2) 逐章生成 — 并行调用（章节只依赖大纲与素材，互相独立；核心章 128K 预算）
    def _gen_section(i: int, title: str, requirements: str) -> tuple[int, str]:
        is_core = "四、模型" in title
        llm_for_section = llm_core_section if is_core else llm_section
        resp = invoke_with_retry(
            llm_for_section,
            [
                HumanMessage(
                    content=WRITING_SECTION_PROMPT.format(
                        outline=outline,
                        section_title=title,
                        section_requirements=requirements,
                        **materials,
                    )
                )
            ],
            task_id=task_id,
            node=f"writing_section_{i + 1}",
        )
        _log_usage(task_id, f"writing_section_{i + 1}", resp)
        sec = _clean_md(resp.content)
        if sec and not sec.startswith("##"):
            sec = f"## {title}\n\n{sec}"
        return i, sec

    from concurrent.futures import ThreadPoolExecutor

    parallelism = max(1, min(get_settings().writing_parallelism, len(paper_sections)))
    with ThreadPoolExecutor(max_workers=parallelism) as _pool:
        _futures = [_pool.submit(_gen_section, i, t, r) for i, (t, r) in enumerate(paper_sections)]
        _results = [f.result() for f in _futures]  # 任一章节失败 → 整体失败，保证论文完整
    _results.sort(key=lambda x: x[0])
    section_texts = [sec for _, sec in _results]
    for i, (title, _req) in enumerate(paper_sections):
        _pub_event(
            task_id,
            "node_progress",
            "writing_agent",
            {"stage": "section", "title": title, "index": i + 1},
        )

    # 3) 摘要最后写（提炼正文真实结果）
    _pub_event(task_id, "node_progress", "writing_agent", {"stage": "abstract"})
    paper_body = "\n\n".join(section_texts)
    _abstract_resp = invoke_with_retry(
        llm_abstract,
        [
            HumanMessage(
                content=WRITING_ABSTRACT_PROMPT.format(outline=outline, paper_body=paper_body)
            )
        ],
        task_id=task_id,
        node="writing_abstract",
    )
    _log_usage(task_id, "writing_abstract", _abstract_resp)
    abstract = _clean_md(_abstract_resp.content)

    # 4) 拼装：标题 + 摘要 + 正文
    paper = f"# {paper_title}\n\n{abstract}\n\n{paper_body}"

    # 5) 红队审校（合规 + 洞察双 gate）
    _pub_event(task_id, "node_progress", "writing_agent", {"stage": "red_team"})
    _rt_resp = invoke_with_retry(
        llm_redteam,
        [HumanMessage(content=RED_TEAM_PROMPT.format(paper=paper))],
        task_id=task_id,
        node="writing_redteam",
    )
    _log_usage(task_id, "writing_redteam", _rt_resp)
    critique = _clean_md(_rt_resp.content)

    # 6) 有实质问题则最小化修订一轮
    if critique and "PASS" not in critique.upper().split("\n")[0]:
        _pub_event(task_id, "node_progress", "writing_agent", {"stage": "revise"})
        _rev_resp = invoke_with_retry(
            llm_revise,
            [HumanMessage(content=WRITING_REVISE_PROMPT.format(paper=paper, critique=critique))],
            task_id=task_id,
            node="writing_revise",
        )
        _log_usage(task_id, "writing_revise", _rev_resp)
        revised = _clean_md(_rev_resp.content)
        if revised and len(revised) > len(paper) // 2:  # 修订结果应大体完整
            paper = revised

    writing_output = paper

    _pub_event(
        task_id,
        "node_end",
        "writing_agent",
        {
            "step": idx + 1,
            "output_length": len(writing_output),
            "red_team": "PASS" if "PASS" in critique.upper().split("\n")[0] else "REVISED",
            "summary": writing_output[:800],
            "title": "论文写作",
            "desc": f"论文 {len(writing_output)} 字"
            + (
                " · 红队审校通过"
                if "PASS" in critique.upper().split("\n")[0]
                else " · 红队修订完成"
            ),
        },
    )

    if state["mode"] == "execute":
        _save_working_memory(
            task_id, "writing", writing_output[:5000], extra={"total_length": len(writing_output)}
        )

    return {
        "writing_output": writing_output,
        "current_step_index": idx,
        "messages": [
            SystemMessage(content=f"[写作Agent] 第{idx + 1}步完成，论文 {len(writing_output)} 字")
        ],
    }


# ============================================================
# 节点: 数据预处理
# ============================================================
def data_preprocessing_agent_node(state: AgentState) -> dict:
    """数据预处理 Agent — 独立 EDA 和数据清洗节点。

    仅在 execute 模式且有数据文件时执行。
    - 多轮 tool loop 调用 run_code 完成数据质量检查、统计摘要、可视化
    - 产出结构化 EDA 报告供后续 modeling/solving 使用
    """
    idx = _next_step(state)
    task_id = state["session_id"]
    _check_cancelled(task_id)

    # 无数据文件时跳过
    data_files = state.get("data_files") or []
    if not data_files and not state.get("data_files_dir"):
        _pub_event(
            task_id,
            "node_end",
            "data_preprocessing_agent",
            {
                "step": idx + 1,
                "skipped": True,
                "summary": "无数据文件，跳过数据预处理",
                "title": "数据预处理",
                "desc": "（无数据，已跳过）",
            },
        )
        return {
            "preprocessed_data": None,
            "current_step_index": idx,
            "messages": [SystemMessage(content=f"[预处理Agent] 第{idx + 1}步跳过（无数据文件）")],
        }

    _pub_event(task_id, "node_start", "data_preprocessing_agent", {"step": idx + 1})
    llm = get_llm("solving", state.get("api_key_config"))  # 复用 solving 的 LLM 配置

    # 注入数据文件目录
    run_code_tool = RunCodeTool()
    run_code_tool.data_files_dir = state.get("data_files_dir", "")

    tools = [run_code_tool] + create_math_tools()
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    model_text = state.get("model_output") or "无模型"

    # 构建数据文件上下文
    data_files_context = ""
    if data_files:
        lines = ["\n## 可用数据文件（已挂载到工作目录，代码中直接用文件名读取）"]
        for df in data_files:
            lines.append(
                f"- `{df.get('filename', '?')}`: "
                f"{df.get('rows', '?')}行, "
                f"列: {', '.join(df.get('columns', []))}"
            )
        data_files_context = "\n".join(lines)

    system_prompt = PREPROCESSING_SYSTEM_PROMPT
    user_prompt = PREPROCESSING_USER_TEMPLATE.format(
        problem=state["problem_raw"],
        model=model_text,
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt + data_files_context),
    ]

    all_images: list[str] = []
    max_rounds = 5

    for _ in range(max_rounds):
        _check_cancelled(task_id)
        response = invoke_with_retry(
            llm_with_tools, messages, task_id=task_id, node="preprocessing_tool"
        )
        _log_usage(task_id, "preprocessing_tool", response)
        messages.append(response)
        # 每轮 LLM 解说文本推给前端（与流式节点的 node_delta 同通道，逐轮累积）
        round_text = getattr(response, "content", "") or ""
        if round_text:
            _pub_event(
                task_id,
                "node_delta",
                "data_preprocessing_agent",
                {"delta": str(round_text)},
            )

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break

        # 协议 v2.1：tool_call（running）→ 执行 → tool_result（id 回声，同一卡片两段更新）
        for tc in tool_calls:
            _pub_event(
                task_id,
                "tool_call",
                "data_preprocessing_agent",
                {
                    "tool_call_id": tool_call_id(tc, tc.get("name")),
                    "tool_name": tc.get("name"),
                    "input": {
                        k: (str(v)[:1500] if k == "code" else v)
                        for k, v in (tc.get("args") or {}).items()
                    },
                    "status": "running",
                },
            )

        def _run_one(tc: dict) -> tuple[str, dict]:
            """执行单个工具，返回 (结果文本, 元信息)。"""
            tool_name = tc.get("name")
            tool_args = tc.get("args") or {}
            tool = tool_map.get(tool_name)
            t0 = time.monotonic()
            if tool is None:
                return (
                    f"未知工具: {tool_name}",
                    {
                        "tool_name": tool_name,
                        "ok": False,
                        "error": f"未知工具: {tool_name}",
                        "duration_ms": 0,
                    },
                )
            try:
                text = tool.invoke(tool_args)
                return text, {
                    "tool_name": tool_name,
                    "ok": True,
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                }
            except Exception as e:  # noqa: BLE001
                return (
                    f"工具执行失败: {e}",
                    {
                        "tool_name": tool_name,
                        "ok": False,
                        "error": str(e)[:200],
                        "duration_ms": int((time.monotonic() - t0) * 1000),
                    },
                )

        from concurrent.futures import ThreadPoolExecutor

        results: dict[str, tuple[str, dict]] = {}

        # run_code 串行（取消事件注入）；其余工具并行 + 超时
        run_code_tool.cancel_event = get_cancel_event(task_id)
        for tc in tool_calls:
            if tc.get("name") != "run_code":
                continue
            tc_id = tool_call_id(tc, "run_code")
            _pub_event(task_id, "code_exec", "data_preprocessing_agent", {"status": "running", "id": tc_id})
            text, meta = _run_one(tc)
            results[tc_id] = (text, meta)
            code_data = parse_code_result(text)
            _pub_event(
                task_id,
                "code_exec",
                "data_preprocessing_agent",
                {
                    "status": "done",
                    "id": tc_id,
                    **code_data,
                    "ok": meta["ok"],
                    "duration_ms": meta["duration_ms"],
                },
            )

        others = [tc for tc in tool_calls if tc.get("name") != "run_code"]
        if others:
            # 不用 with：__exit__ 的 shutdown(wait=True) 会无限 join 已超时放弃的
            # 卡死线程，把整个编排器拖住（审查 P1「超时是假象」）。
            # wait=False 立即返回；cancel_futures 取消队列里尚未开跑的任务。
            _pool = ThreadPoolExecutor(max_workers=min(4, len(others)))
            try:
                _futs: dict[str, tuple] = {
                    tool_call_id(tc, tc.get("name")): (_pool.submit(_run_one, tc), tc.get("name"))
                    for tc in others
                }
                for tc_id, (_fut, tool_name) in _futs.items():
                    try:
                        text, meta = _fut.result(timeout=tool_timeout(tool_name))
                    except TimeoutError:
                        text = f"工具执行超时（{tool_timeout(tool_name):.0f}s）"
                        meta = {
                            "tool_name": tool_name,
                            "ok": False,
                            "error": text,
                            "duration_ms": int(tool_timeout(tool_name) * 1000),
                        }
                    results[tc_id] = (text, meta)
            finally:
                _pool.shutdown(wait=False, cancel_futures=True)

        for tc in tool_calls:
            tc_id = tool_call_id(tc, tc.get("name"))
            tool_name = tc.get("name")
            text, meta = results[tc_id]

            if tool_name == "run_code":
                all_images.extend(_collect_image_urls(text))

            _pub_event(
                task_id,
                "tool_result",
                "data_preprocessing_agent",
                {
                    "tool_call_id": tc_id,
                    "tool_name": tool_name,
                    "preview": text[:1500],
                    "ok": meta["ok"],
                    "duration_ms": meta["duration_ms"],
                    "images": _collect_image_urls(text),
                    **({"error": meta["error"]} if meta.get("error") else {}),
                },
            )

            messages.append(
                ToolMessage(
                    content=text,
                    tool_call_id=tc_id,
                )
            )

    # 最终输出 = 最后一条 AI 文本消息
    final_output = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content and not (getattr(m, "tool_calls", None)):
            final_output = str(m.content)
            break

    if not final_output:
        fallback = llm.invoke(
            messages
            + [
                HumanMessage(
                    content="请停止调用工具，基于以上已获得的分析结果，立即输出结构化 EDA 报告。"
                )
            ]
        )
        _log_usage(task_id, "preprocessing_fallback", fallback)
        final_output = str(fallback.content)

    # 持久化 EDA 图表，并把报告里的临时 run_id URL 改写为持久链接
    _persisted = _persist_task_files(task_id, image_urls=all_images)
    for _old, _new in (_persisted.get("url_map") or {}).items():
        final_output = final_output.replace(_old, _new)

    _pub_event(
        task_id,
        "node_end",
        "data_preprocessing_agent",
        {
            "step": idx + 1,
            "output_length": len(final_output),
            "images_count": len(all_images),
            "summary": final_output[:800],
            "title": "数据预处理",
            "desc": f"EDA 报告 {len(final_output)} 字"
            + (f"，图表 {len(all_images)} 张" if all_images else ""),
        },
    )

    if state["mode"] == "execute":
        _save_working_memory(
            task_id, "preprocessing", final_output, extra={"images_count": len(all_images)}
        )

    return {
        "preprocessed_data": final_output,
        "current_step_index": idx,
        "messages": [
            SystemMessage(
                content=f"[预处理Agent] 第{idx + 1}步完成，"
                f"图表 {len(all_images)} 张，"
                f"输出 {len(final_output)} 字"
            )
        ],
    }


# ============================================================
# 节点: 结果导出
# ============================================================
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
