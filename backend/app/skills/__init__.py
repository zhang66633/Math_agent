"""技能系统：文件即技能（`app/skills/<name>/SKILL.md`）。

用法：
    from app.skills import list_skills, load_skill, resolve_skills, render_skills_section

    summaries = resolve_skills(problem_type="optimization", agent_role="modeling")
    section = render_skills_section(summaries)   # 追加到 system prompt 末尾
"""

from .loader import (
    MAX_SKILL_BODY_CHARS,
    Skill,
    SkillSummary,
    list_skills,
    load_skill,
    render_skills_section,
    resolve_skills,
)

__all__ = [
    "MAX_SKILL_BODY_CHARS",
    "Skill",
    "SkillSummary",
    "list_skills",
    "load_skill",
    "render_skills_section",
    "resolve_skills",
]
