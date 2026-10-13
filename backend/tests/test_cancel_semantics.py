"""任务取消语义回归测试（审计 2026-10-14 P3）。

背景：对已完成/已出错/已取消的任务再调 cancel，旧实现恒返 200「任务已取消」——
幂等无害，但前端会把一个已完成的任务显示成「已取消」，状态是骗人的。
改为 409，让调用方能区分「取消成功」与「没什么可取消」。

运行: 在 backend/ 目录下 `python -m pytest tests/test_cancel_semantics.py -q`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import create_jwt  # noqa: E402
from app.auth.schemas import GitHubUser  # noqa: E402
from app.main import app  # noqa: E402
from app.services.session import get_session_manager  # noqa: E402

OWNER = "cancel_probe"


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_jwt(GitHubUser(id=5, login=OWNER, name='p'))}"}


def _make(status: str) -> str:
    mgr = get_session_manager()
    tid = mgr.create(problem=f"取消语义测试-{status}", mode="execute", owner=OWNER)["task_id"]
    if status != "running":
        mgr.update(tid, status=status)
    return tid


def test_cancel_running_task_still_200():
    tid = _make("running")
    try:
        with TestClient(app) as c:
            r = c.post(f"/api/tasks/{tid}/cancel", headers=_auth())
            assert r.status_code == 200, r.text
            assert get_session_manager().get(tid)["status"] == "cancelled"
    finally:
        get_session_manager().delete(tid)


def test_cancel_completed_task_returns_409():
    """已完成 → 409，且状态不被篡改（修复前是 200 + 状态被改成 cancelled）。"""
    tid = _make("completed")
    try:
        with TestClient(app) as c:
            r = c.post(f"/api/tasks/{tid}/cancel", headers=_auth())
            assert r.status_code == 409, f"应 409，实际 {r.status_code}: {r.text[:120]}"
            assert get_session_manager().get(tid)["status"] == "completed", "终态被篡改"
    finally:
        get_session_manager().delete(tid)


def test_cancel_error_task_returns_409():
    tid = _make("error")
    try:
        with TestClient(app) as c:
            assert c.post(f"/api/tasks/{tid}/cancel", headers=_auth()).status_code == 409
    finally:
        get_session_manager().delete(tid)


def test_cancel_already_cancelled_returns_409():
    tid = _make("cancelled")
    try:
        with TestClient(app) as c:
            assert c.post(f"/api/tasks/{tid}/cancel", headers=_auth()).status_code == 409
    finally:
        get_session_manager().delete(tid)


def test_cancel_other_users_task_still_404():
    """隔离优先于状态判断：他人任务一律 404（不泄露存在性），哪怕是终态。"""
    tid = _make("completed")
    try:
        with TestClient(app) as c:
            r = c.post(f"/api/tasks/{tid}/cancel")  # 匿名/访客
            assert r.status_code == 404, r.text
    finally:
        get_session_manager().delete(tid)
