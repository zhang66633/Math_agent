"""chart-templates 技能回归测试（2026-10 引入）。

守三件事：
  ① SKILL.md 能被技能系统正常解析（frontmatter 合法、name 与目录名一致、有 description）；
  ② 正文不超过 MAX_SKILL_BODY_CHARS——超了会被静默截断，模板就白放了；
  ③ templates/ 下每个 .py 都是合法 Python 且带 apply_chart_style / create_chart 两个入口，
     14 个图型一个不少（防腐烂）。

运行: 在 backend/ 目录下 `python -m pytest tests/test_chart_templates.py -q`
"""

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.skills import list_skills  # noqa: E402
from app.skills.loader import MAX_SKILL_BODY_CHARS, load_skill  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent / "app" / "skills" / "chart-templates"
TEMPLATES_DIR = SKILL_DIR / "templates"

EXPECTED_TYPES = [
    "bar_chart", "box_violin", "bubble_chart", "dual_axis_chart", "grouped_bar_chart",
    "heatmap", "line_chart", "multi_panel_combined", "network_graph",
    "prediction_interval", "radar_chart", "scatter_regression", "stacked_bar_chart",
    "tornado_sensitivity",
]


def test_skill_is_discoverable():
    """技能必须能被 list_skills 发现（否则等于没装）。"""
    names = {s.name for s in list_skills(refresh=True)}
    assert "chart-templates" in names, f"技能未被发现，现有: {sorted(names)}"


def test_skill_body_within_limit():
    """正文不得超过 MAX_SKILL_BODY_CHARS——超了会被 loader 静默截断。"""
    skill = load_skill("chart-templates")
    assert skill is not None, "load_skill 返回 None"
    body = skill.body
    assert body, "技能正文为空"
    assert len(body) <= MAX_SKILL_BODY_CHARS, (
        f"正文 {len(body)} 字符超过上限 {MAX_SKILL_BODY_CHARS}，会被截断；"
        "请把更多模板挪到 templates/ 目录而不是堆进正文"
    )


def test_skill_targets_the_right_agents():
    """只挂 solving / data_preprocessing——这两个节点才真正出图。"""
    summary = next(s for s in list_skills(refresh=True) if s.name == "chart-templates")
    assert set(summary.agents) == {"solving", "data_preprocessing"}, summary.agents


def test_all_templates_present_and_valid():
    """14 个图型一个不少，且都是合法 Python。"""
    files = sorted(TEMPLATES_DIR.glob("*.py"))
    got = [f.stem for f in files]
    missing = set(EXPECTED_TYPES) - set(got)
    extra = set(got) - set(EXPECTED_TYPES)
    assert not missing, f"缺模板: {sorted(missing)}"
    assert not extra, f"多出未知模板: {sorted(extra)}"
    for f in files:
        try:
            ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e:
            raise AssertionError(f"{f.name} 语法错误: {e}")


def test_templates_expose_expected_entrypoints():
    """每个模板都要有 apply_chart_style + create_chart——这是本技能的调用约定。"""
    for f in sorted(TEMPLATES_DIR.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        missing = {"apply_chart_style", "create_chart"} - funcs
        assert not missing, f"{f.name} 缺入口函数 {missing}"


def test_templates_actually_render():
    """真跑一遍：模板必须能出图（不只是语法对）。

    缺 matplotlib/seaborn 整体跳过；单个模板缺它自己的第三方依赖（如 networkx）
    也跳过——本地少装一个可选包不该让 CI 红，但会在摘要里留下 skip 记录。
    """
    pytest.importorskip("matplotlib", reason="缺 matplotlib")
    pytest.importorskip("seaborn", reason="缺 seaborn")

    import importlib.util
    import warnings

    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    rendered = skipped = 0
    for f in sorted(TEMPLATES_DIR.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"tpl_{f.stem}", f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # 测试机无中文字体，Glyph missing 无害
                result = mod.create_chart()
            # 契约：返回 Figure，或 Figure 的可迭代（如 stacked_bar_chart 一次出
            # 绝对值 + 百分比两张）。两种都接受，其余一律算违约。
            figs = result if isinstance(result, (list, tuple)) else [result]
            assert figs, f"{f.name} 没返回任何 Figure"
            for fig in figs:
                assert isinstance(fig, Figure), (
                    f"{f.name} 返回了 {type(fig).__name__}，不是 Figure"
                )
                plt.close(fig)
            rendered += 1
        except ModuleNotFoundError as e:
            skipped += 1
            print(f"  SKIP {f.name}: 缺依赖 {e.name}")
    assert rendered > 0, "一个模板都没跑起来"
    print(f"  渲染成功 {rendered} 个，跳过 {skipped} 个")


if __name__ == "__main__":
    for _fn in [
        test_skill_is_discoverable,
        test_skill_body_within_limit,
        test_skill_targets_the_right_agents,
        test_all_templates_present_and_valid,
        test_templates_expose_expected_entrypoints,
        test_templates_actually_render,
    ]:
        _fn()
        print(f"PASSED {_fn.__name__}")
    print("ALL TESTS PASSED")
