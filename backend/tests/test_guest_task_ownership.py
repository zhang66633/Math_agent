"""访客任务属主回归测试（审计 2026-10-14，安全修复引入的 P0 回归）。

背景：
    用户隔离修复给 SessionManager 加了 owner，但 create_task 当时用
    `apikeys._resolve_user_id`（访客桶 = "guest"，为兼容存量 apikeys.json）
    给**任务**定属主，而所有读取方用 `auth.resolve_user_id`（访客桶 = "default"，
    与 session.DEFAULT_TASK_OWNER 一致）。两个字面量不一致 → 匿名任务一经创建，
    GET /api/tasks/{id} 404、列表里没有、WS 403。

    访客是本站**默认形态**（登录限项目贡献者 ALLOWED_CONTRIBUTORS），所以这个
    回归等于整个方案模式对真实用户不可用。现有 test_user_isolation.py 只覆盖
    登录用户（audit_owner_a/b），访客路径无测试——本文件补上。

运行: 在 backend/ 目录下 `python -m pytest tests/test_guest_task_ownership.py -q`
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.session import get_session_manager  # noqa: E402

_CREATED: list[str] = []


def _stub_key(monkeypatch):
    """让建任务不依赖 apikeys.json 里是否真配了 Key。"""
    import app.api.tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "get_active_api_key", lambda uid=None: {"key": "stub"})
    # 不真跑编排器（会打真实 LLM）；只验证属主链路
    monkeypatch.setattr(tasks_mod, "_run_orchestrator_sync", lambda *a, **k: None)


def _cleanup(task_id: str):
    mgr = get_session_manager()
    mgr.delete(task_id)
    sess_dir = Path(get_settings().project_root) / "data" / "sessions" / task_id
    shutil.rmtree(sess_dir, ignore_errors=True)


def test_guest_can_read_task_it_just_created(monkeypatch):
    """匿名建任务 → 立刻能 GET 到自己，且出现在列表里。"""
    _stub_key(monkeypatch)
    with TestClient(app) as c:
        r = c.post(
            "/api/tasks",
            json={"problem": "访客属主回归测试", "mode": "execute", "files": []},
        )
        assert r.status_code == 200, r.text
        tid = r.json()["task_id"]
        _CREATED.append(tid)
        try:
            # 读自己：必须 200（回归时是 404）
            assert c.get(f"/api/tasks/{tid}").status_code == 200
            # 列表里必须有（回归时缺席）
            assert tid in [t["task_id"] for t in c.get("/api/tasks").json()]
            # 属主必须落在任务命名空间的访客桶 "default"（回归时是 "guest"）
            assert get_session_manager().get_owned(tid, "default") is not None
            assert get_session_manager().get_owned(tid, "guest") is None
        finally:
            _cleanup(tid)


def test_guest_websocket_can_subscribe_own_task(monkeypatch):
    """匿名建的任务，匿名 WS 必须能订阅（回归时 1008 关闭）。"""
    _stub_key(monkeypatch)
    with TestClient(app) as c:
        r = c.post(
            "/api/tasks",
            json={"problem": "访客 WS 回归测试", "mode": "execute", "files": []},
        )
        assert r.status_code == 200, r.text
        tid = r.json()["task_id"]
        _CREATED.append(tid)
        try:
            with c.websocket_connect(f"/api/ws/task/{tid}") as ws:
                msg = ws.receive_json()
                assert msg["task_id"] == tid
        finally:
            _cleanup(tid)


def test_guest_task_still_invisible_to_logged_in_user(monkeypatch):
    """隔离不能反向失效：登录用户看不到访客的任务。"""
    from app.auth import create_jwt
    from app.auth.schemas import GitHubUser

    _stub_key(monkeypatch)
    token = create_jwt(GitHubUser(id=99, login="audit_guest_probe", name="probe"))
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as c:
        r = c.post(
            "/api/tasks",
            json={"problem": "访客隔离回归测试", "mode": "execute", "files": []},
        )
        tid = r.json()["task_id"]
        _CREATED.append(tid)
        try:
            # 匿名（属主本人）能读
            assert c.get(f"/api/tasks/{tid}").status_code == 200
            # 登录用户看不到访客的任务
            assert c.get(f"/api/tasks/{tid}", headers=headers).status_code == 404
        finally:
            _cleanup(tid)


def teardown_module(module):
    for tid in _CREATED:
        _cleanup(tid)
