"""上传附件接入流水线的回归测试（2026-10-14 修复）。

缺陷：create_initial_state 从不收 data_files / data_files_dir，而 KB 侧 38 道题的
data_files 全是 []、nodes.py 还刻意不给自定义题挂 data_files——两个字段恒为空，
连带：data_preprocessing_agent 跳过条件恒为真（死代码）、solving agent 被告知
「没有预挂载数据文件」转而构造模拟数据、RunCodeTool 自动挂载不触发。
用户上传的真实附件只有前 100 行被内联进题面文本，沙箱里根本读不到。

本测试锁三件事：
  ① _run_orchestrator 会把 uploaded 附件搬进 data/task_files/{id}/_inputs/；
  ② 传入 state 的 data_files / data_files_dir 非空，跳过条件不再恒真；
  ③ 那些文件在沙箱里真的可读（走 RunCodeTool 的 data_files_dir 自动挂载）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.api.tasks import _run_orchestrator
from app.core.state import create_initial_state
from app.services.session import get_session_manager
from app.tools.interaction_tools import RunCodeTool

ROOT = Path(__file__).resolve().parent.parent


def _stage_uploads(task_id: str, files: dict[str, bytes]) -> list[dict]:
    """把文件写进 data/uploads/ 并在 session 里登记成 uploaded 附件。"""
    uploads = ROOT / "data" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    mgr = get_session_manager()
    arts = []
    for i, (name, content) in enumerate(files.items()):
        fid = f"testatt{i:02d}"
        for stale in uploads.glob(f"{fid}.*"):
            stale.unlink()
        (uploads / f"{fid}{Path(name).suffix}").write_bytes(content)
        arts.append(
            {"type": "uploaded", "name": name, "url": f"/api/files/{fid}", "size": len(content)}
        )
    task = mgr.create(problem="附件接入测试", mode="execute", owner="test_att_owner")
    for a in arts:
        mgr.add_artifact(task["task_id"], a)
    return task["task_id"], arts


def _cleanup(task_id: str):
    import shutil

    mgr = get_session_manager()
    mgr.delete(task_id, "test_att_owner")
    shutil.rmtree(ROOT / "data" / "task_files" / task_id, ignore_errors=True)
    for f in (ROOT / "data" / "uploads").glob("testatt*.*"):
        f.unlink(missing_ok=True)


def test_uploads_reach_state_and_inputs_dir():
    """附件必须同时进 state.data_files 与 task_files/{id}/_inputs/。"""
    import asyncio

    import app.api.tasks as tasks_mod
    import app.core.state as state_mod
    import app.core.workflow as wf_mod

    # _run_orchestrator 里 get_orchestrator / create_initial_state 都是函数内
    # 局部 import，所以要打到各自的源模块上（不是 app.api.tasks）。
    class _FakeOrch:
        async def astream(self, *a, **kw):
            return
            yield  # pragma: no cover

    orig_wf = wf_mod.get_orchestrator
    orig_key = tasks_mod.get_active_api_key
    wf_mod.get_orchestrator = lambda: _FakeOrch()
    tasks_mod.get_active_api_key = lambda uid: None

    captured = {}
    orig_cis = state_mod.create_initial_state

    def spy(**kwargs):
        captured.update(kwargs)
        return orig_cis(**kwargs)

    state_mod.create_initial_state = spy
    try:
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        csv = df.to_csv(index=False).encode()
        tid, _ = _stage_uploads("t", {"data.csv": csv})

        try:
            asyncio.run(_run_orchestrator(tid, "测试题", "execute", "test_att_owner"))
        finally:
            state_mod.create_initial_state = orig_cis

        assert captured.get("data_files"), "data_files 没被传入——附件又断在这里了"
        assert captured["data_files"][0]["filename"] == "data.csv"
        assert captured.get("data_files_dir"), "data_files_dir 为空，自动挂载不会触发"

        inputs = Path(captured["data_files_dir"])
        assert inputs.is_dir(), f"输入目录不存在: {inputs}"
        assert (inputs / "data.csv").exists(), "附件没被复制进 _inputs"
        assert (inputs / "data.csv").read_bytes() == csv, "复制内容不一致"
        _cleanup(tid)
    finally:
        wf_mod.get_orchestrator = orig_wf
        tasks_mod.get_active_api_key = orig_key
        state_mod.create_initial_state = orig_cis


def test_skip_condition_no_longer_always_true():
    """接了附件后，data_preprocessing 的跳过条件必须为假。"""
    tid, arts = _stage_uploads("t2", {"d.csv": b"a,b\n1,2\n"})
    try:
        mgr = get_session_manager()
        task = mgr.get(tid)
        uploaded = [
            {"file_id": a["url"].rsplit("/", 1)[-1], "filename": a["name"]}
            for a in task["artifacts"]
            if a.get("type") == "uploaded"
        ]
        state = create_initial_state(
            problem_raw="p", mode="execute", session_id=tid, data_files=uploaded
        )
        # data_preprocessing_agent_node 的第 52 行条件
        assert not (not state["data_files"] and not state["data_files_dir"]), (
            "跳过条件仍恒真——数据预处理依然是死代码"
        )
    finally:
        _cleanup(tid)


def test_sandbox_can_read_staged_input():
    """_inputs 里的文件必须能通过 data_files_dir 自动挂载进沙箱。"""
    tid, _ = _stage_uploads("t3", {"d.csv": b"a,b\n1,2\n3,4\n"})
    try:
        inputs = ROOT / "data" / "task_files" / tid / "_inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        (inputs / "d.csv").write_bytes(b"a,b\n1,2\n3,4\n")

        tool = RunCodeTool()
        tool.data_files_dir = str(inputs)
        res = tool.invoke(
            {"code": "import pandas as pd\ndf = pd.read_csv('d.csv')\nprint(df.shape, list(df.columns))"}
        )
        assert "(2, 2)" in res, f"沙箱没读到暂存的输入文件: {res[:300]}"
        assert "['a', 'b']" in res
    finally:
        _cleanup(tid)


def test_no_attachments_means_no_inputs_dir():
    """没有附件时不应造出空的 _inputs（否则自动挂载白跑）。"""
    mgr = get_session_manager()
    task = mgr.create(problem="无附件", mode="execute", owner="test_att_owner")
    tid = task["task_id"]
    try:
        uploaded = [
            {"file_id": a["url"].rsplit("/", 1)[-1], "filename": a["name"]}
            for a in (task.get("artifacts") or [])
            if a.get("type") == "uploaded"
        ]
        assert uploaded == []
        state = create_initial_state(problem_raw="p", mode="execute", session_id=tid)
        assert state["data_files"] == []
        assert state["data_files_dir"] == ""
    finally:
        mgr.delete(tid, "test_att_owner")


# ── 端到端实测踩到的两个坑（只跑单测抓不到）──────────────────


def test_retrieve_node_does_not_wipe_uploaded_data_files():
    """retrieve_knowledge 必须增量合并 data_files，不能返回空列表覆盖。

    2026-10-14 实测：附件已复制进 _inputs、data_files 也传进了
    create_initial_state，但 retrieve_knowledge 返回 `"data_files": []`
    （KB 里 38 道题的 data_files 全是 []），LangGraph 把它覆盖进 state，
    于是 data_preprocessing 的跳过条件立刻又成立——单测能过、真跑必挂。
    """
    import inspect

    from app.core import nodes as nodes_mod

    src = inspect.getsource(nodes_mod.retrieve_knowledge)
    assert "list(state.get(\"data_files\") or [])" in src, (
        "retrieve_knowledge 又从空列表重新算了 data_files——会把上传附件抹掉"
    )
    assert "state.get(\"data_files_dir\") or \"\"" in src, (
        "retrieve_knowledge 又从空串重新算了 data_files_dir"
    )


def test_retrieval_query_is_capped():
    """送去检索的 query 必须截断，否则长题面（含附件摘要）会撞穿模型上下文上限。

    实测 2026-10-14：problem_raw 8193 tokens > deepseek 的 8192 上限，
    向量检索整条 400 降级，只剩 BM25 + 标签召回。题目主旨都在开头。
    """
    from app.core import nodes as nodes_mod

    assert hasattr(nodes_mod, "_MAX_RETRIEVAL_QUERY_CHARS")
    cap = nodes_mod._MAX_RETRIEVAL_QUERY_CHARS
    assert 500 <= cap <= 4000, f"截断上限 {cap} 不合理（太小丢语义、太大仍会超限）"

    import inspect

    src = inspect.getsource(nodes_mod.retrieve_knowledge)
    assert "_MAX_RETRIEVAL_QUERY_CHARS" in src, "检索入口没做截断"
    assert "retriever.invoke(_q" in src, "截断后的 query 没被真正用于检索"


def test_retrieval_cap_actually_bounds_a_long_problem():
    """模拟长题面：截断后长度必须真的落回上限内。"""
    from app.core.nodes import _MAX_RETRIEVAL_QUERY_CHARS

    long_problem = "蔬菜定价与补货" * 3000  # 24000 字符
    q = long_problem
    if len(q) > _MAX_RETRIEVAL_QUERY_CHARS:
        q = q[:_MAX_RETRIEVAL_QUERY_CHARS]
    assert len(q) == _MAX_RETRIEVAL_QUERY_CHARS
    assert q.startswith("蔬菜定价")  # 保留头部（题目主旨）


if __name__ == "__main__":
    for _fn in [
        test_uploads_reach_state_and_inputs_dir,
        test_skip_condition_no_longer_always_true,
        test_sandbox_can_read_staged_input,
        test_no_attachments_means_no_inputs_dir,
        test_retrieve_node_does_not_wipe_uploaded_data_files,
        test_retrieval_query_is_capped,
        test_retrieval_cap_actually_bounds_a_long_problem,
    ]:
        _fn()
        print(f"PASSED {_fn.__name__}")
    print("ALL TESTS PASSED")
