"""任务删除 + parquet 数据链路回归测试（2026-10-14 补）。

背景：
- `/api/tasks` 此前只有 GET/POST，**任务只能增不能删**。前端「删除会话」删的
  只是 conversation，与任务无关——实测用户删完前端，API 仍返回 78 个任务，
  sessions.json 已 3.89 MB 且只增不减。
- 项目自带的 2023C 竞赛数据是 parquet，但 pyarrow 缺失 + 三处扩展名白名单
  （上传 / 附件摘要 / 沙箱自动挂载）都不含 .parquet，导致 DATA_README.md 里
  设计的「沙箱内 pd.read_parquet() 秒级加载」从来没通过。

本测试锁：删除端点的行为与属主校验、三处白名单都含 parquet、pyarrow 已声明。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.files import ALLOWED_EXTENSIONS  # noqa: E402
from app.main import app  # noqa: E402
from app.services.session import get_session_manager  # noqa: E402

OWNER = "test_del_owner"


def _mk(problem: str = "待删除的测试任务") -> str:
    return get_session_manager().create(problem=problem, mode="execute", owner=OWNER)["task_id"]


def _auth() -> dict[str, str]:
    from app.auth import create_jwt
    from app.auth.schemas import GitHubUser

    return {"Authorization": f"Bearer {create_jwt(GitHubUser(id=9, login=OWNER))}"}


# ── 删除端点 ───────────────────────────────────────────


def test_delete_endpoint_exists():
    with TestClient(app) as c:
        # 不存在的任务 → 404（而不是 405，证明路由真的注册了）
        r = c.delete("/api/tasks/nonexistent1", headers=_auth())
        assert r.status_code == 404, f"期望 404，实际 {r.status_code}"


def test_delete_removes_task_and_disk_data():
    """删任务必须同时清掉三处磁盘产物，只删记录算没删干净。"""
    tid = _mk()
    root = Path(__file__).resolve().parent.parent / "data"
    # 造出三类产物
    tf = root / "task_files" / tid
    tf.mkdir(parents=True, exist_ok=True)
    (tf / "fig.png").write_bytes(b"x")
    (root / "task_events" / f"{tid}.jsonl").write_text("{}\n", encoding="utf-8")
    sd = root / "sessions" / tid
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "problem_doc.md").write_text("x", encoding="utf-8")

    try:
        with TestClient(app) as c:
            r = c.delete(f"/api/tasks/{tid}", headers=_auth())
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["success"] is True
            # 三类产物都应报已清理
            assert set(body["cleaned"]) >= {"task_files", "task_events", "sessions"}, body

        assert get_session_manager().get(tid) is None, "sessions.json 里的记录没删"
        assert not tf.exists(), "task_files 没删"
        assert not (root / "task_events" / f"{tid}.jsonl").exists(), "task_events 没删"
        assert not sd.exists(), "sessions 工作记忆没删"
    finally:
        for p in (tf, root / "task_events" / f"{tid}.jsonl", sd):
            if p.is_dir():
                import shutil

                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file():
                p.unlink(missing_ok=True)


def test_delete_requires_ownership():
    """别人的任务删不掉，且回 404 而非 403（不泄露 task_id 是否存在）。"""
    tid = _mk("别人的任务")
    try:
        with TestClient(app) as c:
            from app.auth import create_jwt
            from app.auth.schemas import GitHubUser

            other = {"Authorization": f"Bearer {create_jwt(GitHubUser(id=10, login='intruder'))}"}
            r = c.delete(f"/api/tasks/{tid}", headers=other)
            assert r.status_code == 404, f"他人竟能删/探测到任务：{r.status_code}"
            # 未登录同样不行
            assert c.delete(f"/api/tasks/{tid}").status_code == 404
            # 任务还在
            assert get_session_manager().get(tid) is not None
    finally:
        get_session_manager().delete(tid, OWNER)


def test_session_manager_delete_checks_owner():
    from app.services.session import SessionManager

    m = SessionManager(persist_path=None)
    a = m.create(problem="a", owner="alice")["task_id"]
    b = m.create(problem="b", owner="bob")["task_id"]
    assert m.delete(a, owner="bob") is False, "delete 未校验属主"
    assert m.get(a) is not None
    assert m.delete(a, owner="alice") is True
    assert m.get(a) is None
    assert m.get(b) is not None


# ── parquet 数据链路 ───────────────────────────────────


def test_parquet_in_upload_whitelist():
    assert ".parquet" in ALLOWED_EXTENSIONS, "上传白名单仍不含 .parquet"


def test_parquet_in_sandbox_autoscale_whitelist():
    """沙箱自动挂载数据文件的白名单必须含 .parquet。

    这一条是 2023C 预计算数据从未进过沙箱的直接原因——白名单写死在
    interaction_tools.py 里，之前只有 xlsx/csv/tsv/txt/json/dat。
    """
    import inspect

    from app.tools import interaction_tools

    src = inspect.getsource(interaction_tools.RunCodeTool._run)
    assert '".parquet"' in src, "沙箱自动挂载白名单仍不含 .parquet"
    assert '".md"' in src, "沙箱自动挂载白名单仍不含 .md（DATA_README 进不去）"


def test_parquet_attachment_extraction():
    """parquet 附件必须走结构化摘要，不能掉进「按文本读」把二进制解成乱码。"""
    import io as _io

    import pandas as pd

    from app.api.tasks import _extract_attachment_text

    # 造一个 parquet 并放进 uploads 目录（_extract_attachment_text 按 file_id glob）
    df = pd.DataFrame({"品类": ["叶菜", "瓜果"], "损耗率": [0.12, 0.05]})
    buf = _io.BytesIO()
    df.to_parquet(buf)

    uploads = Path(__file__).resolve().parent.parent / "data" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    file_id = "testparquet1"
    for stale in uploads.glob(f"{file_id}.*"):
        stale.unlink()
    target = uploads / f"{file_id}.parquet"
    target.write_bytes(buf.getvalue())

    try:
        text = _extract_attachment_text(file_id, "损耗率.parquet")
        # 结构化摘要的特征：有「行 × 列」形状信息、有表头、不是二进制乱码
        assert "2 行 × 2 列" in text, f"parquet 没走结构化分支: {text[:200]}"
        assert "叶菜" in text, "parquet 内容没被读取"
        assert "\ufffd" not in text and "\\x" not in text, "疑似二进制乱码"
    finally:
        target.unlink(missing_ok=True)


def test_pyarrow_declared_in_pyproject():
    """pyarrow 必须声明为核心依赖（本地与 CI 都能装到）。"""
    import tomllib

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert any(d.startswith("pyarrow") for d in deps), f"pyarrow 不在核心依赖: {deps}"


def test_pyarrow_in_sandbox_dockerfile():
    """沙箱镜像必须装 pyarrow，否则容器里 read_parquet 照样 ImportError。"""
    dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile.sandbox"
    txt = dockerfile.read_text(encoding="utf-8")
    assert "pyarrow" in txt, "Dockerfile.sandbox 未安装 pyarrow"


if __name__ == "__main__":
    for _fn in [
        test_delete_endpoint_exists,
        test_delete_removes_task_and_disk_data,
        test_delete_requires_ownership,
        test_session_manager_delete_checks_owner,
        test_parquet_in_upload_whitelist,
        test_parquet_in_sandbox_autoscale_whitelist,
        test_parquet_attachment_extraction,
        test_pyarrow_declared_in_pyproject,
        test_pyarrow_in_sandbox_dockerfile,
    ]:
        _fn()
        print(f"PASSED {_fn.__name__}")
    print("ALL TESTS PASSED")
