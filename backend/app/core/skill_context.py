"""技能装配桥接层 —— 把 `app/skills` 接到各 agent 节点上。

职责分离（对应 DSH skill 的「列举不读正文、按需加载」）：

- **目录**：`plan_execution` 阶段按题型解析一次，写进 `AgentState.active_skills`，
  前端因此能显示「本题装配了哪些技能」；
- **正文**：各 agent 节点按自己的角色过滤目录，**只有真正要用的技能才读正文**，
  再追加到 system prompt 末尾。

技能是**附加建议**，不改写原有指令的强制条款，也不影响图拓扑与回退语义。
"""

from __future__ import annotations

import logging

from app.skills import render_skills_section, resolve_skills

logger = logging.getLogger(__name__)


def catalog_for_problem(problem_type: str | None) -> list[str]:
    """该题型命中的技能名列表（写入 state，也用于事件流展示）。"""
    return [s.name for s in resolve_skills(problem_type)]


def section_for_agent(
    problem_type: str | None,
    agent_role: str,
    active: list[str] | None = None,
) -> str:
    """返回应追加到 system prompt 末尾的技能小节；无命中返回空串。

    `active` 是规划阶段定下的技能目录：非空时只装配其中的技能，保证同一任务
    前后节点看到的技能集合一致（旧任务恢复时目录为空则按题型重新解析）。
    """
    summaries = resolve_skills(problem_type, agent_role)
    if active:
        allowed = set(active)
        summaries = [s for s in summaries if s.name in allowed]

    section = render_skills_section(summaries)
    if section:
        logger.debug("为 %s 装配技能：%s", agent_role, [s.name for s in summaries])
    return section
