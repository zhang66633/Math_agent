"""nodes.py 节点级表征测试（无 LLM 桩测试，god-files #31 深度拆分的前置）。

运行: 在 backend/ 目录下 `python -m pytest tests/test_nodes.py -q`
      或直接 `python tests/test_nodes.py`。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage  # noqa: E402

import app.core.nodes as nodes  # noqa: E402
from app.core.agents import (  # noqa: E402
    analysis,
    data_preprocessing,
    export_results,
    modeling,
    solving,
    verification,
    writing,
)
from app.core.node_helpers import (  # noqa: E402
    _clean_md,
    _extract_code_block,
    _extract_json,
    _next_step,
)

# ── 桩：替代真实 LLM 调用 ─────────────────────────────────────────
# agent 节点实现拆到 core/agents/<agent>.py 后，各模块命名空间各自持有
# get_llm 引用（from ..llm.factory import get_llm）——打桩必须覆盖所有
# 持有该引用的模块，否则拆分布局会让桩静默失效。
_LLM_MODULES = [
    nodes,
    analysis,
    modeling,
    solving,
    verification,
    writing,
    data_preprocessing,
    export_results,
]


class _FakeLLM:
    def __init__(self, text: str):
        self._text = text

    def invoke(self, messages):
        return AIMessage(content=self._text)

    def stream(self, messages):
        # 流式路径（invoke_streaming_with_retry 使用）：单 chunk 返回全文
        yield AIMessage(content=self._text)

    def bind_tools(self, tools):
        return self


def _stub_llm(text: str):
    for module in _LLM_MODULES:
        if hasattr(module, "get_llm"):
            module.get_llm = lambda role, key=None: _FakeLLM(text)


def _base_state(**overrides) -> dict:
    state = {
        "session_id": "test_nodes",
        "problem_raw": "测试问题",
        "problem_type": "optimization",
        "mode": "teach",  # teach 模式跳过工作记忆落盘与沙箱
        "execution_plan": ["analysis", "modeling", "solving", "verification", "writing"],
        "current_step_index": 0,
        "max_retries": 3,
        "retry_count": 0,
        "kb_methods": [],
        "kb_templates": [],
        "kb_papers": [],
        "kb_problems": [],
        "analysis_output": "",
        "model_output": "",
        "solving_output": "",
        "api_key_config": None,
    }
    state.update(overrides)
    return state


# ── 纯辅助函数 ──────────────────────────────────────────────


def test_next_step_increments():
    assert _next_step({"current_step_index": -1}) == 0
    assert _next_step({"current_step_index": 0}) == 1


def test_extract_code_block():
    assert "print(1)" in _extract_code_block("```python\nprint(1)\n```")
    assert _extract_code_block("no code here") == ""


def test_clean_md():
    # _clean_md 只负责剥离 LLM 输出外层的 ``` 围栏，不做行内格式转换
    assert _clean_md("```markdown\n正文内容\n```") == "正文内容"
    assert _clean_md("```\n正文\n```") == "正文"
    assert _clean_md("**加粗** text") == "**加粗** text"


def test_extract_json():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"b": 2}\n```') == {"b": 2}
    assert _extract_json("not json") == {}


# ── 验证节点回退状态机 ───────────────────────────────────────


def test_verification_pass_no_rollback():
    _stub_llm('{"verdict": "PASS"}')
    out = nodes.verification_agent_node(_base_state(current_step_index=2))
    assert out["verification_passed"] is True
    assert out["rollback_target"] is None
    assert out["retry_count"] == 0
    assert out["current_step_index"] == 3  # 指针停在 verification 位置


def test_verification_fail_rolls_back_once_within_budget():
    _stub_llm('{"verdict": "FAIL", "rollback_target": "modeling"}')
    out = nodes.verification_agent_node(_base_state(current_step_index=2))
    assert out["verification_passed"] is False
    assert out["rollback_target"] == "modeling"
    assert out["retry_count"] == 1
    # 指针拨回 modeling 前一位（配合 _next_step 递增语义，modeling 入点=1）
    assert out["current_step_index"] == 0


def test_verification_fail_exhausted_no_rollback():
    _stub_llm('{"verdict": "FAIL", "rollback_target": "modeling"}')
    out = nodes.verification_agent_node(_base_state(current_step_index=2, retry_count=3))
    assert out["rollback_target"] is None
    assert out["retry_count"] == 4
    assert out["current_step_index"] == 3  # 指针不再回拨，继续 writing


def test_verification_hallucinated_target_sanitized():
    _stub_llm('{"verdict": "FAIL", "rollback_target": "analysis"}')
    out = nodes.verification_agent_node(_base_state(current_step_index=2))
    assert out["rollback_target"] == "modeling"  # 白名单外一律收敛为 modeling


def test_verification_nested_json_fenced():
    """嵌套 JSON + ```json 围栏 + 后续散文 → _extract_verdict_json 仍能判定。"""
    _stub_llm(
        '```json\n{"verdict": "FAIL", "rollback_target": "solving", "details": {"layer": 1}}\n```\n'
        "后续分析正文……"
    )
    out = nodes.verification_agent_node(_base_state(current_step_index=2))
    assert out["rollback_target"] == "solving"  # 白名单内，原样返回
    assert out["retry_count"] == 1


def test_verification_json_among_prose():
    _stub_llm('判定结果：{"verdict": "PASS"} 其余分析文字')
    out = nodes.verification_agent_node(_base_state(current_step_index=2))
    assert out["verification_passed"] is True
    assert out["rollback_target"] is None


def test_modeling_consumes_rollback_flag():
    _stub_llm("模型输出内容")
    out = nodes.modeling_agent_node(
        _base_state(
            current_step_index=0,
            rollback_target="modeling",
        )
    )
    assert out["rollback_target"] is None  # 消费回退标志，防自循环
    assert out["current_step_index"] == 1


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {e!r}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
