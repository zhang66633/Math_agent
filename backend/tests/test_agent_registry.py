"""Agent 注册表（core/agent_registry.yaml）回归测试。

守护「单一真源」这个性质：注册表、router 的计划映射、workflow 的节点函数三者
必须始终一致——此前正是三份手抄映射表漂移过。
"""

from pathlib import Path

import pytest

from app.core import agent_registry as registry
from app.core.agent_registry import (
    AgentRegistryError,
    agent_node_functions,
    agent_node_map,
    load_entry,
    load_registry,
)
from app.core.router import AGENT_NODES
from app.core.workflow import build_orchestrator


def test_registry_is_non_empty() -> None:
    assert len(load_registry()) >= 7


def test_ids_and_nodes_unique() -> None:
    specs = load_registry()
    assert len({s.id for s in specs}) == len(specs)
    assert len({s.node for s in specs}) == len(specs)


def test_router_map_derives_from_registry() -> None:
    """router 的 AGENT_NODES 必须等于注册表派生的映射（同一份真源）。"""
    assert AGENT_NODES == agent_node_map()


def test_workflow_node_functions_match_registry() -> None:
    """workflow 装载的节点函数集合必须与注册表声明的节点集合一致。"""
    assert set(agent_node_functions()) == {s.node for s in load_registry()}


def test_entries_are_importable_and_callable() -> None:
    for spec in load_registry():
        assert callable(load_entry(spec)), f"{spec.id} 的 entry 不可调用：{spec.entry}"


def test_model_roles_are_known() -> None:
    for spec in load_registry():
        if spec.model_role is not None:
            assert spec.model_role in registry.VALID_MODEL_ROLES


def test_graph_builds_from_registry() -> None:
    assert build_orchestrator() is not None


def test_skill_flags_only_on_llm_agents() -> None:
    """装配技能的节点必须真的调用 LLM（export_results 是纯文件打包，不该装配）。"""
    for spec in load_registry():
        if spec.skills:
            assert spec.model_role is not None, f"{spec.id} 不调用 LLM 却声明了技能装配"


def test_invalid_model_role_fails_fast(tmp_path: Path, monkeypatch) -> None:
    bad = tmp_path / "agent_registry.yaml"
    bad.write_text(
        "agents:\n"
        "  - id: a\n"
        "    node: a_node\n"
        "    label: 甲\n"
        "    entry: app.core.agents.analysis:analysis_agent_node\n"
        "    model_role: not-a-role\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "REGISTRY_PATH", bad)
    registry.reset_cache()
    try:
        with pytest.raises(AgentRegistryError):
            registry.load_registry()
    finally:
        registry.reset_cache()


def test_missing_entry_fails_fast(tmp_path: Path, monkeypatch) -> None:
    bad = tmp_path / "agent_registry.yaml"
    bad.write_text(
        "agents:\n  - id: a\n    node: a_node\n    label: 甲\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "REGISTRY_PATH", bad)
    registry.reset_cache()
    try:
        with pytest.raises(AgentRegistryError):
            registry.load_registry()
    finally:
        registry.reset_cache()


def test_duplicate_id_fails_fast(tmp_path: Path, monkeypatch) -> None:
    bad = tmp_path / "agent_registry.yaml"
    bad.write_text(
        "agents:\n"
        "  - id: dup\n"
        "    node: a_node\n"
        "    label: 甲\n"
        "    entry: app.core.agents.analysis:analysis_agent_node\n"
        "  - id: dup\n"
        "    node: b_node\n"
        "    label: 乙\n"
        "    entry: app.core.agents.modeling:modeling_agent_node\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "REGISTRY_PATH", bad)
    registry.reset_cache()
    try:
        with pytest.raises(AgentRegistryError):
            registry.load_registry()
    finally:
        registry.reset_cache()


def test_unimportable_entry_raises() -> None:
    spec = registry.AgentSpec(
        id="ghost",
        node="ghost_agent",
        label="幽灵",
        entry="app.core.agents.nonexistent:ghost_node",
        model_role=None,
        skills=False,
        uses_tools=False,
        rollback=False,
        order=99,
    )
    with pytest.raises(AgentRegistryError):
        load_entry(spec)
