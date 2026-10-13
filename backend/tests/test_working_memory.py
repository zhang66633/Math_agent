"""Working Memory 回归测试（审计 2026-10-14 P1：问题状态文档是死功能）。

背景：
    问题状态文档曾经由「LLM 整体重写」实现，靠
    `asyncio.get_event_loop().run_in_executor(...)` 触发。图节点跑在 langgraph
    线程池 worker 里，那些线程没有运行中的事件循环 → get_event_loop() 恒抛
    RuntimeError → 被 except 静默跳过。生产环境里从未生效过一次：所有真实任务的
    problem_doc.md 都是 init_session 写的初始模板（七个章节全「（待完成）」），
    而 get_problem_doc() 当时全仓库零调用方——花了钱还没人看。

    现在改为确定性拼装（refresh_problem_doc）：只读检查点 JSON、纯文件 IO、同步
    调用，并通过 GET /api/tasks/{id}/status 的 problem_doc 字段暴露。
    本文件的用例就是这两件事的护栏：**节点保存后文档必须真的更新**。

运行: 在 backend/ 目录下 `python -m pytest tests/test_working_memory.py -q`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.session import get_session_manager  # noqa: E402
from app.services.working_memory import STAGE_ORDER, WorkingMemory  # noqa: E402


def _wm(task_id: str) -> WorkingMemory:
    return WorkingMemory(task_id)


# ── 确定性拼装 ──────────────────────────────────────────


def test_refresh_assembles_from_checkpoints():
    tid = "wm_unit_refresh"
    wm = _wm(tid)
    wm.init_session("某工厂生产甲乙两种产品，如何分配使利润最大？")
    try:
        # 初始：全部待完成
        assert "（待完成）" in wm.get_problem_doc()

        wm.save_checkpoint("classify", '{"problem_type": "optimization"}', extra={})
        wm.save_checkpoint("analysis", "本题为资源分配优化问题，决策变量为产品产量。")
        doc = wm.refresh_problem_doc()

        # 已完成的阶段带上摘要，未完成的仍待完成
        assert "optimization" in doc
        assert "资源分配优化问题" in doc
        assert doc.count("（待完成）") == len(STAGE_ORDER) - 2
        # 原始问题从 meta.json 读回（曾被 init_session 写进模板后就再也读不回来）
        assert "某工厂生产甲乙两种产品" in doc
        # 落盘生效
        assert wm.get_problem_doc() == doc
    finally:
        _cleanup(tid)


def test_refresh_is_idempotent_and_no_llm():
    """重复刷新结果一致；且拼装版不得再依赖 LLM（否则每任务多 7 次真实调用）。"""
    tid = "wm_unit_idem"
    wm = _wm(tid)
    wm.init_session("测试题")
    try:
        wm.save_checkpoint("modeling", "建立线性规划模型。")
        first = wm.refresh_problem_doc()
        second = wm.refresh_problem_doc()
        assert first == second
    finally:
        _cleanup(tid)


def test_implementation_does_not_call_llm():
    """护栏：working_memory.py 不得再依赖 LLM。

    死功能时代的实现每次刷新都打一次 LLM（约 7 次/任务）却没人读；拼装版必须
    保持零 LLM 依赖，否则「修好一个死功能」会变成「每任务多花一笔钱」。
    注意用「赋值/定义」形态匹配——文件顶部的墓碑注释会提到旧名字，不能简单 not in。
    """
    src = (
        get_settings().project_root / "app" / "services" / "working_memory.py"
    ).read_text(encoding="utf-8")
    assert "get_llm" not in src, "working_memory 又 import 了 LLM 工厂——拼装版应保持零依赖"
    assert "REWRITE_PROMPT =" not in src, "LLM 重写 prompt 又回来了"
    assert "def update_problem_doc" not in src, "LLM 整体重写方法又回来了"
    # 正面护栏：拼装入场
    assert "def refresh_problem_doc" in src


def test_refresh_noop_without_session():
    """没有 init_session 的会话直接返回空串，不建目录不写文件。"""
    wm = _wm("wm_unit_absent")
    assert wm.refresh_problem_doc() == ""


# ── 节点侧：保存后文档必须真的更新（死功能回归护栏） ──────────


def test_save_working_memory_actually_updates_doc():
    """_save_working_memory 之后 problem_doc 必须含该阶段内容。

    修复前这里恒失败：异步重写在无事件循环的 worker 线程里被跳过，
    文档永远是初始模板。
    """
    from app.core.node_helpers import _save_working_memory

    tid = "wm_unit_node"
    wm = _wm(tid)
    wm.init_session("节点侧回归测试题")
    try:
        _save_working_memory(tid, "solving", "最优解 x*=(12,8)，Z*=236。")
        doc = wm.get_problem_doc()
        assert "最优解 x*=(12,8)" in doc, "节点保存后问题状态文档没有更新——死功能回归"
    finally:
        _cleanup(tid)


def test_status_endpoint_exposes_problem_doc():
    """GET /api/tasks/{id}/status 必须带上 problem_doc（给它一个真实读者）。"""
    from app.auth import create_jwt
    from app.auth.schemas import GitHubUser

    tid = get_session_manager().create(problem="status 端点回归", mode="execute", owner="wm_probe")[
        "task_id"
    ]
    wm = _wm(tid)
    wm.init_session("status 端点回归")
    token = create_jwt(GitHubUser(id=7, login="wm_probe", name="probe"))
    try:
        wm.save_checkpoint("verification", "灵敏度分析表明模型鲁棒。")
        with TestClient(app) as c:
            r = c.get(f"/api/tasks/{tid}/status", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["problem_doc"]
            assert "灵敏度分析表明模型鲁棒" in body["problem_doc"]
    finally:
        _cleanup(tid)
        get_session_manager().delete(tid)


def _cleanup(task_id: str):
    import shutil

    shutil.rmtree(get_settings().project_root / "data" / "sessions" / task_id, ignore_errors=True)
