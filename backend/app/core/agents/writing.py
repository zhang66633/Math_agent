"""Writing agent node - dynamic paper section splitting and per-section writing.

Split from core/nodes.py: nodes.py keeps only orchestration nodes
(classify/retrieve/plan/format_response) plus re-exports.
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.core.state import AgentState

from ..llm.factory import get_llm
from ..node_helpers import (
    _check_cancelled,
    _clean_md,
    _log_usage,
    _next_step,
    _pub_event,
    _save_working_memory,
    invoke_with_retry,
)
from ..prompts.writing import (
    RED_TEAM_PROMPT,
    WRITING_ABSTRACT_PROMPT,
    WRITING_OUTLINE_PROMPT,
    WRITING_REVISE_PROMPT,
    WRITING_SECTION_PROMPT,
    WRITING_TEACH_SYSTEM_PROMPT,
    WRITING_TEACH_USER_TEMPLATE,
)

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
