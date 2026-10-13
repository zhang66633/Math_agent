"""技能系统：文件即技能（file-as-skill）。

设计借鉴 DSH `dsh-skill` 的「摘要与正文分离」：
- 列举阶段只读 YAML frontmatter（`SkillSummary`），不读正文；
- 只有真正要装配进提示词时才读正文（`load_skill`）；
- 单个技能格式非法只跳过它并告警，**不中断流水线**。

技能目录布局（每个技能一个子目录）：

    app/skills/<name>/SKILL.md

`SKILL.md` 以 YAML frontmatter 开头，正文为给模型的指令文本。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent
SKILL_FILENAME = "SKILL.md"

# 与 classifier 输出的 problem_type 对齐
VALID_PROBLEM_TYPES = frozenset(
    {
        "optimization",
        "prediction",
        "evaluation",
        "statistics",
        "graph_theory",
        "differential_equation",
        "composite",
    }
)

# 可被装配技能的执行型 agent 角色（planner/classifier 等编排角色不装配）
VALID_AGENT_ROLES = frozenset(
    {"analysis", "modeling", "data_preprocessing", "solving", "verification", "writing"}
)

# 单份技能正文的字符上限：技能是「指令」不是「资料」，超限说明该拆成 references
MAX_SKILL_BODY_CHARS = 6000

# name -> (mtime, summary)；文件改动后自动失效（对应 DSH 的「无 TTL、提供方驱动失效」简化版）
_SUMMARY_CACHE: dict[str, tuple[float, SkillSummary]] = {}


@dataclass(frozen=True)
class SkillSummary:
    """技能摘要：列举阶段的唯一产物，不含正文。"""

    name: str
    description: str
    problem_types: tuple[str, ...]
    agents: tuple[str, ...]
    auto: bool
    priority: int
    path: Path

    def matches(self, problem_type: str | None, agent_role: str | None = None) -> bool:
        """该技能是否适用于给定题型与角色。

        - `problem_type` 为空表示题型未知：只命中「不限题型」的技能；
        - `agent_role` 为空表示**不限角色**（规划阶段生成技能目录时用），
          只有给定角色时才按 `agents` 过滤。
        """
        if not self.auto:
            return False
        if self.problem_types and problem_type not in self.problem_types:
            return False
        if agent_role is not None and self.agents and agent_role not in self.agents:
            return False
        return True


@dataclass(frozen=True)
class Skill:
    """技能全文：摘要 + 正文。"""

    summary: SkillSummary
    body: str


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """拆分 `---` 包裹的 YAML frontmatter 与正文。

    注意：正文里也可能出现 `---` 分隔线，因此只认**第一个**闭合标记，
    不能按 `---` 全量切分。
    """
    stripped = text.lstrip("\ufeff").replace("\r\n", "\n")
    if not stripped.startswith("---"):
        raise ValueError("缺少 frontmatter（文件应以 --- 开头）")
    rest = stripped[3:]
    end = rest.find("\n---")
    if end == -1:
        raise ValueError("frontmatter 未正确闭合（缺少结束的 ---）")
    raw_meta = rest[:end]
    body = rest[end + 4 :]
    meta = yaml.safe_load(raw_meta) or {}
    if not isinstance(meta, dict):
        raise ValueError("frontmatter 必须是 YAML 映射")
    return meta, body.strip()


def _as_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return ()


def _parse_summary(path: Path) -> SkillSummary | None:
    """解析单个 SKILL.md 的摘要；不可用时返回 None（只告警，不抛错）。"""
    try:
        meta, _body = _split_frontmatter(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — 单个技能坏掉不应影响整体
        logger.warning("技能解析失败，已跳过：%s（%s）", path, exc)
        return None

    name = str(meta.get("name") or "").strip()
    description = str(meta.get("description") or "").strip()
    if not name:
        logger.warning("技能缺少 name，已跳过：%s", path)
        return None
    if name != path.parent.name:
        logger.warning("技能 name(%s) 与目录名(%s) 不一致，已跳过：%s", name, path.parent.name, path)
        return None
    if not description:
        logger.warning("技能缺少 description，已跳过：%s", path)
        return None

    problem_types = _as_tuple(meta.get("problem_types"))
    unknown_types = [t for t in problem_types if t not in VALID_PROBLEM_TYPES]
    if unknown_types:
        logger.warning("技能 %s 含未知 problem_types %s，已忽略这些取值", name, unknown_types)
        problem_types = tuple(t for t in problem_types if t in VALID_PROBLEM_TYPES)

    agents = _as_tuple(meta.get("agents"))
    unknown_agents = [a for a in agents if a not in VALID_AGENT_ROLES]
    if unknown_agents:
        logger.warning("技能 %s 含未知 agents %s，已忽略这些取值", name, unknown_agents)
        agents = tuple(a for a in agents if a in VALID_AGENT_ROLES)

    return SkillSummary(
        name=name,
        description=description,
        problem_types=problem_types,
        agents=agents,
        auto=bool(meta.get("auto", True)),
        priority=int(meta.get("priority", 0) or 0),
        path=path,
    )


def list_skills(*, refresh: bool = False) -> list[SkillSummary]:
    """列出全部可用技能摘要（按 priority 降序、name 升序）。不读正文。"""
    if not SKILLS_DIR.exists():
        return []

    found: dict[str, tuple[float, SkillSummary]] = {}
    for skill_file in sorted(SKILLS_DIR.glob(f"*/{SKILL_FILENAME}")):
        try:
            mtime = skill_file.stat().st_mtime
        except OSError:
            continue
        cached = _SUMMARY_CACHE.get(skill_file.parent.name)
        if not refresh and cached and cached[0] == mtime:
            found[skill_file.parent.name] = cached
            continue
        summary = _parse_summary(skill_file)
        if summary is None:
            continue
        found[skill_file.parent.name] = (mtime, summary)

    if refresh:
        _SUMMARY_CACHE.clear()
    _SUMMARY_CACHE.update(found)

    summaries = [s for _mtime, s in found.values()]
    summaries.sort(key=lambda s: (-s.priority, s.name))
    return summaries


def load_skill(name: str) -> Skill | None:
    """按名加载技能全文。名称无效返回 None（不抛错）。"""
    summary = next((s for s in list_skills() if s.name == name), None)
    if summary is None:
        return None
    try:
        _meta, body = _split_frontmatter(summary.path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("技能 %s 正文读取失败：%s", name, exc)
        return None
    if len(body) > MAX_SKILL_BODY_CHARS:
        logger.warning(
            "技能 %s 正文 %d 字符，超过 %d 上限，已截断（该拆成 references 了）",
            name,
            len(body),
            MAX_SKILL_BODY_CHARS,
        )
        body = body[:MAX_SKILL_BODY_CHARS] + "\n\n…（技能正文过长已截断）"
    return Skill(summary=summary, body=body)


def resolve_skills(
    problem_type: str | None,
    agent_role: str | None = None,
    *,
    extra_names: list[str] | None = None,
) -> list[SkillSummary]:
    """按题型 + 角色选出适用技能；extra_names 为显式点名的技能（忽略 auto 开关）。"""
    summaries = list_skills()
    picked: list[SkillSummary] = [
        s for s in summaries if s.matches(problem_type, agent_role)
    ]

    for name in extra_names or []:
        hit = next((s for s in summaries if s.name == name), None)
        if hit and hit not in picked:
            picked.append(hit)

    return picked


def render_skills_section(summaries: list[SkillSummary]) -> str:
    """把技能正文渲染成附加在 system prompt 末尾的小节；无技能时返回空串。"""
    if not summaries:
        return ""
    blocks: list[str] = []
    for summary in summaries:
        skill = load_skill(summary.name)
        if skill is None:
            continue
        blocks.append(f"### 技能：{skill.summary.name}\n（{skill.summary.description}）\n\n{skill.body}")
    if not blocks:
        return ""
    return "\n\n## 专业技能\n\n以下技能按本题题型自动装配，请优先遵循其中的流程与约束。\n\n" + "\n\n".join(blocks)
