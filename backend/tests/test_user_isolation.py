"""任务与学习数据的用户隔离回归测试（审计 2026-10 P0-1 / P0-2）。

背景：
  P0-1  tasks.py 整组路由注入了 user 却从不使用 → 无鉴权可读/取消他人任务；
        ws.py 也只 decode 不校验 → 可订阅他人任务的实时执行过程。
  P0-2  learning_routes / profile_routes 把 user_id 当请求参数 → 可越权
        读写任意 user_id 的学习进度、错题本与成就。

这两个缺陷都是「代码看着有鉴权、实际没生效」型，所以测试一律走真实 HTTP
（TestClient + 真实 SessionManager），不停留在单元层面。

运行: 在 backend/ 目录下 `python -m pytest tests/test_user_isolation.py -q`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import create_jwt  # noqa: E402
from app.auth.schemas import GitHubUser  # noqa: E402
from app.main import app  # noqa: E402
from app.services.session import get_session_manager  # noqa: E402

OWNER_A = "audit_owner_a"
OWNER_B = "audit_owner_b"


def _token(login: str) -> str:
    return create_jwt(GitHubUser(id=1, login=login, name=login))


def _auth(login: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(login)}"}


def _reset_tasks():
    """清掉审计用的任务，避免污染真实 sessions.json。"""
    mgr = get_session_manager()
    for t in mgr.list_all():
        if t.get("owner") in (OWNER_A, OWNER_B):
            mgr.delete(t["task_id"])


def _make_task(owner: str, problem: str) -> str:
    return get_session_manager().create(problem=problem, mode="execute", owner=owner)["task_id"]


# ── P0-1 任务隔离 ─────────────────────────────────────


def test_task_list_only_returns_own_tasks():
    tid_a = _make_task(OWNER_A, "A 的私密赛题原文")
    tid_b = _make_task(OWNER_B, "B 的私密赛题原文")
    try:
        with TestClient(app) as c:
            r = c.get("/api/tasks", headers=_auth(OWNER_A))
            assert r.status_code == 200, r.text
            ids = {t["task_id"] for t in r.json()}
            assert tid_a in ids, "自己的任务没列出来"
            assert tid_b not in ids, "列表泄露了他人任务"
            assert all("B 的私密赛题原文" not in t.get("problem", "") for t in r.json())
    finally:
        get_session_manager().delete(tid_a)
        get_session_manager().delete(tid_b)


def test_task_detail_not_readable_by_other_user():
    tid = _make_task(OWNER_B, "只有 B 能看")
    try:
        with TestClient(app) as c:
            # 未登录（访客）
            assert c.get(f"/api/tasks/{tid}").status_code == 404
            # 登录但非属主
            assert c.get(f"/api/tasks/{tid}", headers=_auth(OWNER_A)).status_code == 404
            # 属主本人
            assert c.get(f"/api/tasks/{tid}", headers=_auth(OWNER_B)).status_code == 200
    finally:
        get_session_manager().delete(tid)


def test_task_messages_events_files_status_blocked_for_others():
    tid = _make_task(OWNER_B, "B 的任务")
    try:
        with TestClient(app) as c:
            ha = _auth(OWNER_A)
            for path in (
                f"/api/tasks/{tid}/messages",
                f"/api/tasks/{tid}/events",
                f"/api/tasks/{tid}/files",
                f"/api/tasks/{tid}/status",
            ):
                r = c.get(path, headers=ha)
                assert r.status_code == 404, f"{path} 未做属主校验 → {r.status_code}"
            # 属主本人放行
            hb = _auth(OWNER_B)
            for path in (
                f"/api/tasks/{tid}/messages",
                f"/api/tasks/{tid}/events",
                f"/api/tasks/{tid}/files",
                f"/api/tasks/{tid}/status",
            ):
                assert c.get(path, headers=hb).status_code == 200, path
    finally:
        get_session_manager().delete(tid)


def test_cancel_task_blocked_for_others():
    tid = _make_task(OWNER_B, "B 的任务")
    try:
        with TestClient(app) as c:
            r = c.post(f"/api/tasks/{tid}/cancel", headers=_auth(OWNER_A))
            assert r.status_code == 404, f"他人竟能取消我的任务 → {r.status_code}"
            # 任务状态未被篡改
            task = get_session_manager().get(tid)
            assert task["status"] == "running", f"状态被改成 {task['status']}"
            # 属主本人可以取消
            assert c.post(f"/api/tasks/{tid}/cancel", headers=_auth(OWNER_B)).status_code == 200
    finally:
        get_session_manager().delete(tid)


def test_export_and_package_blocked_for_others():
    tid = _make_task(OWNER_B, "B 的任务")
    get_session_manager().update(tid, final_response="# 论文\n正文")
    try:
        with TestClient(app) as c:
            ha = _auth(OWNER_A)
            assert c.get(f"/api/tasks/{tid}/export", headers=ha).status_code == 404
            assert c.get(f"/api/tasks/{tid}/package", headers=ha).status_code == 404
            assert c.get(f"/api/tasks/{tid}/export", headers=_auth(OWNER_B)).status_code == 200
    finally:
        get_session_manager().delete(tid)


def test_websocket_rejected_for_non_owner():
    tid = _make_task(OWNER_B, "B 的任务")
    try:
        with TestClient(app) as c:
            # 非属主：服务端未 accept 即 close(1008)，connect 阶段就应断开
            try:
                with c.websocket_connect(f"/api/ws/task/{tid}?token={_token(OWNER_A)}"):
                    raised = False
                raised = False
            except Exception:
                raised = True
            assert raised, "非属主竟能订阅他人任务的 WS 频道"

            # 属主本人可以连上
            with c.websocket_connect(f"/api/ws/task/{tid}?token={_token(OWNER_B)}") as ws:
                msg = ws.receive_json()
                assert msg["event"] == "connected"
    finally:
        get_session_manager().delete(tid)


# ── P0-2 学习数据隔离 ────────────────────────────────


def test_learning_user_id_cannot_be_forged():
    """把 user_id 写在 body 里应被忽略，不得写入他人账号。"""
    with TestClient(app) as c:
        # 未登录 → 落 guest 桶；伪造 user_id=audit_owner_b 应无效
        r = c.post(
            "/api/learning/units/writer_struct_01/complete",
            json={"user_id": OWNER_B},
        )
        assert r.status_code == 200, r.text

        from app.services.learning_store import get_learning_store

        store = get_learning_store()
        leaked = [
            x
            for x in store.list_events(OWNER_B)
            if x["unit_id"] == "writer_struct_01" and x["event_type"] == "learn"
        ]
        assert not leaked, "伪造的 user_id 生效了——IDOR 仍存在"

        # 清理访客桶里本次写入的事件
        with store._get_conn() as conn:
            conn.execute(
                "DELETE FROM learning_events WHERE user_id=? AND unit_id=? AND event_type='learn'",
                ("default", "writer_struct_01"),
            )
            conn.commit()


def test_quiz_mistakes_user_id_query_ignored():
    """query 里的 user_id 不得再决定读哪个桶（与不带该参数的结果必须一致）。"""
    with TestClient(app) as c:
        base = c.get("/api/learning/quiz/mistakes").json()
        forged = c.get(f"/api/learning/quiz/mistakes?user_id={OWNER_B}").json()
        assert forged == base, "user_id 参数仍在生效——IDOR 未修净"


def test_profile_scoped_by_login():
    with TestClient(app) as c:
        ra = c.post("/api/profile/diagnose", json={"role": "modeler"}, headers=_auth(OWNER_A))
        rb = c.post("/api/profile/diagnose", json={"role": "writer"}, headers=_auth(OWNER_B))
        assert ra.status_code == rb.status_code == 200

        pa = c.get("/api/profile", headers=_auth(OWNER_A)).json()["profile"]
        pb = c.get("/api/profile", headers=_auth(OWNER_B)).json()["profile"]
        assert pa["user_id"] == OWNER_A, pa
        assert pb["user_id"] == OWNER_B, pb
        assert pa["roles"] != pb["roles"], "两个账号的画像串了"


# ── SessionManager 属主访问器 ─────────────────────────


def test_session_manager_owner_accessors():
    from app.services.session import SessionManager

    mgr = SessionManager(persist_path=None)
    a = mgr.create(problem="a", owner=OWNER_A)["task_id"]
    b = mgr.create(problem="b", owner=OWNER_B)["task_id"]

    assert mgr.get_owned(a, OWNER_A) is not None
    assert mgr.get_owned(a, OWNER_B) is None, "get_owned 未校验属主"
    assert mgr.get_owned("nope", OWNER_A) is None

    owned = {t["task_id"] for t in mgr.list_for_owner(OWNER_A)}
    assert owned == {a}, f"list_for_owner 返回了别人的任务: {owned}"

    assert mgr.cancel(b, owner=OWNER_A) is False, "cancel 未校验属主"
    assert mgr.get(b)["status"] == "running"
    assert mgr.cancel(b, owner=OWNER_B) is True


def test_legacy_task_without_owner_treated_as_guest():
    """存量无 owner 字段的任务归 guest，登录用户看不到。"""
    from app.services.session import SessionManager

    mgr = SessionManager(persist_path=None)
    tid = mgr.create(problem="legacy")["task_id"]
    del mgr._tasks[tid]["owner"]  # 模拟存量数据

    assert mgr.get_owned(tid, "default") is not None
    assert mgr.get_owned(tid, OWNER_A) is None


def _teardown():
    _reset_tasks()


def teardown_module(module):
    _teardown()


if __name__ == "__main__":
    for _fn in [
        test_task_list_only_returns_own_tasks,
        test_task_detail_not_readable_by_other_user,
        test_task_messages_events_files_status_blocked_for_others,
        test_cancel_task_blocked_for_others,
        test_export_and_package_blocked_for_others,
        test_websocket_rejected_for_non_owner,
        test_learning_user_id_cannot_be_forged,
        test_quiz_mistakes_user_id_query_ignored,
        test_profile_scoped_by_login,
        test_session_manager_owner_accessors,
        test_legacy_task_without_owner_treated_as_guest,
    ]:
        _fn()
        print(f"PASSED {_fn.__name__}")
    _teardown()
    print("ALL TESTS PASSED")
