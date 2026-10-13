"""技能系统（app/skills）回归测试。

守护三件事：内置技能可用、按题型/角色匹配正确、坏技能只跳过不中断流水线。
"""

from pathlib import Path

from app.skills import loader
from app.skills.loader import (
    list_skills,
    load_skill,
    render_skills_section,
    resolve_skills,
)

EXPECTED_BUILTINS = {
    "optimization-modeling",
    "prediction-modeling",
    "evaluation-modeling",
    "sensitivity-analysis",
    "paper-structure",
    "chart-standards",
}


def test_builtin_skills_all_load() -> None:
    names = {s.name for s in list_skills()}
    assert EXPECTED_BUILTINS <= names


def test_every_skill_has_description() -> None:
    """description 是匹配依据，不能为空。"""
    for summary in list_skills():
        assert summary.description.strip()


def test_summary_carries_no_body() -> None:
    """摘要阶段不读正文（DSH skill 的「列举不读正文」）。"""
    for summary in list_skills():
        assert not hasattr(summary, "body")


def test_resolve_matches_problem_type() -> None:
    names = {s.name for s in resolve_skills("optimization", "modeling")}
    assert "optimization-modeling" in names
    assert "evaluation-modeling" not in names
    assert "prediction-modeling" not in names


def test_resolve_matches_agent_role() -> None:
    assert {s.name for s in resolve_skills("optimization", "verification")} == {
        "sensitivity-analysis"
    }
    assert {s.name for s in resolve_skills("optimization", "writing")} == {"paper-structure"}
    # 求解与数据预处理节点负责出图，因此拿到图表规范（两者同一份技能）
    assert {s.name for s in resolve_skills("optimization", "solving")} == {"chart-standards"}
    assert {s.name for s in resolve_skills("optimization", "data_preprocessing")} == {
        "chart-standards"
    }


def test_catalog_without_role_is_not_filtered_by_agents() -> None:
    """回归（2026-10-13 端到端发现）：规划阶段以 agent_role=None 生成技能目录时，
    不得被 agents 字段过滤掉——此前该 bug 让所有技能目录恒为空。"""
    names = {s.name for s in resolve_skills("optimization", None)}
    assert "optimization-modeling" in names
    assert "sensitivity-analysis" in names
    assert "paper-structure" in names


def test_catalog_excludes_other_problem_types() -> None:
    names = {s.name for s in resolve_skills("optimization", None)}
    assert "evaluation-modeling" not in names
    assert "prediction-modeling" not in names


def test_unknown_problem_type_falls_back_to_role_skills() -> None:
    """题型未知时，不限题型的角色技能仍应命中。"""
    assert {s.name for s in resolve_skills(None, "verification")} == {"sensitivity-analysis"}


def test_render_section_includes_body_and_header() -> None:
    section = render_skills_section(resolve_skills("optimization", "modeling"))
    assert "## 专业技能" in section
    assert "三件套必须齐全" in section


def test_render_empty_for_no_skills() -> None:
    assert render_skills_section([]) == ""


def test_load_unknown_skill_returns_none() -> None:
    assert load_skill("no-such-skill") is None


def test_skill_body_within_cap() -> None:
    """技能是指令不是资料，超限应拆 references（这里守护内置技能不超限）。"""
    for summary in list_skills():
        skill = load_skill(summary.name)
        assert skill is not None
        assert len(skill.body) <= loader.MAX_SKILL_BODY_CHARS


def test_invalid_skills_are_skipped_not_raised(tmp_path: Path, monkeypatch) -> None:
    """缺 name / name 与目录不一致 / 无 frontmatter → 跳过该技能，不抛异常。"""
    root = tmp_path / "skills"
    cases = {
        "missing-name": "---\ndescription: 没有 name\n---\n正文",
        "name-mismatch": "---\nname: another-name\ndescription: 名字不一致\n---\n正文",
        "no-frontmatter": "这里直接是正文，没有 frontmatter",
    }
    for dirname, content in cases.items():
        skill_file = root / dirname / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(content, encoding="utf-8")

    monkeypatch.setattr(loader, "SKILLS_DIR", root)
    loader._SUMMARY_CACHE.clear()
    assert list_skills(refresh=True) == []


def test_unknown_enum_values_are_dropped(tmp_path: Path, monkeypatch) -> None:
    """未知 problem_types / agents 取值只剔除该值，技能本身仍可用。"""
    root = tmp_path / "skills"
    skill_file = root / "demo" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\n"
        "name: demo\n"
        "description: 演示技能\n"
        "problem_types: [optimization, not-a-type]\n"
        "agents: [modeling, not-a-role]\n"
        "---\n正文",
        encoding="utf-8",
    )

    monkeypatch.setattr(loader, "SKILLS_DIR", root)
    loader._SUMMARY_CACHE.clear()
    summaries = list_skills(refresh=True)
    assert [s.name for s in summaries] == ["demo"]
    assert summaries[0].problem_types == ("optimization",)
    assert summaries[0].agents == ("modeling",)


def test_cache_invalidated_on_file_change(tmp_path: Path, monkeypatch) -> None:
    """文件改动后摘要必须刷新（对应 DSH 的提供方驱动失效）。"""
    root = tmp_path / "skills"
    skill_file = root / "cache-demo" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: cache-demo\ndescription: 第一版\n---\n正文", encoding="utf-8"
    )

    monkeypatch.setattr(loader, "SKILLS_DIR", root)
    loader._SUMMARY_CACHE.clear()
    assert list_skills(refresh=True)[0].description == "第一版"

    skill_file.write_text(
        "---\nname: cache-demo\ndescription: 第二版\n---\n正文", encoding="utf-8"
    )
    import os

    stat = skill_file.stat()
    os.utime(skill_file, (stat.st_atime, stat.st_mtime + 10))
    assert list_skills()[0].description == "第二版"
