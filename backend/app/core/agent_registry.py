"""Agent 注册表 —— `agent_registry.yaml` 是 agent 定义的唯一真源。

设计参考 DSH `dsh-agent-preset`：定义外置、单一真源、启动即校验（fail-fast）。
代码侧全部由此派生：

- `core/router.py` 的计划步骤映射（`AGENT_NODES`）；
- `core/workflow.py` 的节点函数装载与条件边目标。

加一个 agent = 「写一个节点模块 + 在 YAML 里加一条」，不必再改 router / workflow，
也不会再出现三份手抄映射表各自漂移的情况。
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).resolve().parent / "agent_registry.yaml"

# 与 config.Settings 里按角色配置的模型字段一一对应（classifier/planner/analysis/...）
VALID_MODEL_ROLES = frozenset(
    {
        "classifier",
        "planner",
        "analysis",
        "modeling",
        "solving",
        "verification",
        "writing",
        "chat",
    }
)

REQUIRED_FIELDS = ("id", "node", "label", "entry")


class AgentRegistryError(RuntimeError):
    """注册表配置错误 —— fail-fast，不带病启动。"""


@dataclass(frozen=True)
class AgentSpec:
    """一个 agent 节点的注册信息。"""

    id: str
    node: str
    label: str
    entry: str
    model_role: str | None
    skills: bool
    uses_tools: bool
    rollback: bool
    order: int


def _require_str(raw: dict, key: str, index: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AgentRegistryError(f"agents[{index}] 缺少必填字段 {key}")
    return value.strip()


def _parse_spec(raw: object, index: int) -> AgentSpec:
    if not isinstance(raw, dict):
        raise AgentRegistryError(f"agents[{index}] 必须是映射")

    agent_id = _require_str(raw, "id", index)
    node = _require_str(raw, "node", index)
    label = _require_str(raw, "label", index)
    entry = _require_str(raw, "entry", index)

    if ":" not in entry:
        raise AgentRegistryError(f"agents[{index}].entry 必须是 '模块:属性' 形式，收到 {entry!r}")

    model_role = raw.get("model_role")
    if model_role is not None:
        model_role = str(model_role).strip() or None
        if model_role and model_role not in VALID_MODEL_ROLES:
            raise AgentRegistryError(
                f"agents[{index}].model_role 取值非法：{model_role!r}"
                f"（合法值：{', '.join(sorted(VALID_MODEL_ROLES))}）"
            )

    return AgentSpec(
        id=agent_id,
        node=node,
        label=label,
        entry=entry,
        model_role=model_role,
        skills=bool(raw.get("skills", False)),
        uses_tools=bool(raw.get("uses_tools", False)),
        rollback=bool(raw.get("rollback", False)),
        order=index,
    )


@lru_cache(maxsize=1)
def load_registry() -> tuple[AgentSpec, ...]:
    """读取并校验注册表（进程内缓存）。任何配置错误直接抛 AgentRegistryError。"""
    if not REGISTRY_PATH.exists():
        raise AgentRegistryError(f"未找到注册表文件：{REGISTRY_PATH}")

    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    raw_agents = data.get("agents")
    if not isinstance(raw_agents, list) or not raw_agents:
        raise AgentRegistryError("注册表缺少非空的 agents 列表")

    specs = tuple(_parse_spec(raw, i) for i, raw in enumerate(raw_agents))

    for field in ("id", "node"):
        seen: dict[str, int] = {}
        for spec in specs:
            value = getattr(spec, field)
            if value in seen:
                raise AgentRegistryError(f"{field} 重复：{value!r}")
            seen[value] = spec.order

    logger.debug("已加载 agent 注册表：%d 个节点", len(specs))
    return specs


def reset_cache() -> None:
    """清空缓存（测试或热更新用）。"""
    load_registry.cache_clear()


def agent_node_map() -> dict[str, str]:
    """计划步骤名 -> 图节点名（router 的 AGENT_NODES 即由此派生）。"""
    return {spec.id: spec.node for spec in load_registry()}


def node_specs() -> dict[str, AgentSpec]:
    """图节点名 -> 注册信息。"""
    return {spec.node: spec for spec in load_registry()}


def spec_for_id(agent_id: str) -> AgentSpec | None:
    return next((spec for spec in load_registry() if spec.id == agent_id), None)


def spec_for_node(node: str) -> AgentSpec | None:
    return node_specs().get(node)


def load_entry(spec: AgentSpec) -> Callable[..., Any]:
    """按 `entry` 动态装载节点函数（模块:属性）。失败即抛错，不静默。"""
    module_name, _, attr = spec.entry.partition(":")
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 — 配置错误必须让启动失败
        raise AgentRegistryError(f"agent {spec.id} 的模块无法导入：{module_name}（{exc}）") from exc
    try:
        fn = getattr(module, attr)
    except AttributeError as exc:
        raise AgentRegistryError(f"agent {spec.id} 的属性不存在：{module_name}:{attr}") from exc
    if not callable(fn):
        raise AgentRegistryError(f"agent {spec.id} 的 entry 不可调用：{spec.entry}")
    return fn


def agent_node_functions() -> dict[str, Callable[..., Any]]:
    """图节点名 -> 节点函数（workflow 注册用）。"""
    return {spec.node: load_entry(spec) for spec in load_registry()}
