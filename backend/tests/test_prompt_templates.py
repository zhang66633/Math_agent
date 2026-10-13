"""提示词模板渲染回归测试。

背景（2026-10-13）：方案模式的 planner 节点曾因 ``PLANNER_SYSTEM_PROMPT`` 里含 JSON
输出示例（``{"step": "analysis", ...}``），被 ``str.format`` 当成占位符解析，
运行到 plan_execution 就抛 ``KeyError: '"step"'``，整条流水线无法启动。
该问题由端到端压测发现（单元测试全绿也没拦住，因为没人渲染这个模板）。

这里锁死两件事：
1. 安全渲染函数 ``render_prompt`` 不被 JSON 花括号影响；
2. planner 提示词必须继续走 ``render_prompt``，不得改回 ``.format``。
"""

import string
from pathlib import Path

from app.core.prompts._shared import render_prompt
from app.core.prompts.planner import PLANNER_SYSTEM_PROMPT

NODES_PATH = Path(__file__).resolve().parents[1] / "app" / "core" / "nodes.py"


def test_render_prompt_keeps_json_braces() -> None:
    """JSON 示例必须原样保留，占位符必须被替换。"""
    out = render_prompt(
        PLANNER_SYSTEM_PROMPT,
        methods="方法A",
        templates="模板B",
        papers="论文C",
        problems="真题D",
        experiences="经验E",
    )
    assert '"step": "analysis"' in out
    assert '"reason"' in out
    assert "{methods}" not in out
    assert "方法A" in out and "经验E" in out


def test_render_prompt_leaves_unknown_placeholders() -> None:
    """未提供的键保持原样，避免误删模板内容。"""
    assert render_prompt("A {x} B {y}", x=1) == "A 1 B {y}"


def test_render_prompt_handles_empty_values() -> None:
    """空值也要正常替换（检索无结果时会传空串）。"""
    out = render_prompt(PLANNER_SYSTEM_PROMPT, methods="", templates="", papers="", problems="", experiences="")
    assert "{methods}" not in out


def test_render_prompt_rejects_nothing_when_template_has_illegal_field_names() -> None:
    """即使模板含非法字段名（JSON 键），render_prompt 也不应抛异常。"""
    fields = [f for _, f, _, _ in string.Formatter().parse(PLANNER_SYSTEM_PROMPT) if f]
    illegal = [f for f in fields if not f.isidentifier()]
    assert illegal, "planner 模板应含 JSON 示例（否则本回归测试失去意义）"
    render_prompt(PLANNER_SYSTEM_PROMPT)


def test_nodes_uses_render_prompt_for_planner() -> None:
    """守护：nodes.py 不得对 PLANNER_SYSTEM_PROMPT 使用 .format（会重新引入 KeyError）。"""
    src = NODES_PATH.read_text(encoding="utf-8")
    assert "PLANNER_SYSTEM_PROMPT.format(" not in src
