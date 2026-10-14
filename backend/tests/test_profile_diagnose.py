"""画像 diagnose 合并语义 + 角色切换器写入链路（审计 2026-10-14 第 11.2 节）。

背景：GET /profile 的 roles 只有 /profile/diagnose 一个写入口，而前端从不调用
→ roles 恒为空 → 首页「继续学习」卡（按 roles.length 判断）永远不显示。
修法：角色切换器每次切角色调一次 diagnose；同时把 diagnose 从「覆盖」改成
「合并」——否则切换器每调一次就把用户在一次完整诊断里填的目标冲成默认值。

运行: 在 backend/ 目录下 `python -m pytest tests/test_profile_diagnose.py -q`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.profile_routes import _profiles  # noqa: E402
from app.main import app  # noqa: E402

OWNER = "diag_probe"


def _auth() -> dict[str, str]:
    from app.auth import create_jwt
    from app.auth.schemas import GitHubUser

    return {"Authorization": f"Bearer {create_jwt(GitHubUser(id=11, login=OWNER, name='p'))}"}


def _reset():
    _profiles.pop(OWNER, None)


def test_role_only_call_sets_roles():
    """只传 role：roles 写进去，goal 保持默认（首次创建）。"""
    _reset()
    try:
        with TestClient(app) as c:
            r = c.post("/api/profile/diagnose", json={"role": "writer"}, headers=_auth())
            assert r.status_code == 200, r.text
            p = r.json()["profile"]
            assert [x["role"] for x in p["roles"]] == ["writer"]
            assert p["roles"][0]["is_primary"] is True
            assert p["goal"]["competition"] == "国赛"  # 默认值
    finally:
        _reset()


def test_role_only_call_preserves_existing_goal():
    """关键护栏：先做一次完整诊断（带目标），再只切角色——目标不许被冲掉。"""
    _reset()
    try:
        with TestClient(app) as c:
            r1 = c.post(
                "/api/profile/diagnose",
                json={"role": "modeler", "goal": "美赛", "weekly_hours": 25},
                headers=_auth(),
            )
            assert r1.status_code == 200
            assert r1.json()["profile"]["goal"]["competition"] == "美赛"

            # 角色切换器就是这样调的：只带 role
            r2 = c.post("/api/profile/diagnose", json={"role": "programmer"}, headers=_auth())
            assert r2.status_code == 200
            p2 = r2.json()["profile"]
            assert [x["role"] for x in p2["roles"]] == ["programmer"]
            assert p2["goal"]["competition"] == "美赛", "切角色把用户的目标冲掉了"
            assert p2["goal"]["weekly_hours"] == 25, "切角色把每周时长冲掉了"
    finally:
        _reset()


def test_partial_goal_fields_merge_independently():
    """只给 goal 不给 weekly_hours（或反之）时，另一个字段保留现值。"""
    _reset()
    try:
        with TestClient(app) as c:
            c.post(
                "/api/profile/diagnose",
                json={"role": "modeler", "goal": "研赛", "weekly_hours": 30},
                headers=_auth(),
            )
            r = c.post(
                "/api/profile/diagnose", json={"role": "modeler", "goal": "兴趣"}, headers=_auth()
            )
            goal = r.json()["profile"]["goal"]
            assert goal["competition"] == "兴趣"
            assert goal["weekly_hours"] == 30
    finally:
        _reset()


def test_self_assessment_still_applied():
    _reset()
    try:
        with TestClient(app) as c:
            r = c.post(
                "/api/profile/diagnose",
                json={
                    "role": "modeler",
                    "self_assessment": {
                        "math_level": 4,
                        "programming_level": 2,
                        "writing_level": 3,
                        "modeling_experience": 5,
                    },
                },
                headers=_auth(),
            )
            sa = r.json()["profile"]["self_assessment"]
            assert sa["math_level"] == 4 and sa["modeling_experience"] == 5
    finally:
        _reset()


def test_profile_read_back_reflects_role():
    """GET /profile 能读回角色——这正是首页「继续学习」卡的判据。"""
    _reset()
    try:
        with TestClient(app) as c:
            c.post("/api/profile/diagnose", json={"role": "writer"}, headers=_auth())
            r = c.get("/api/profile", headers=_auth())
            p = r.json()["profile"]
            assert p["roles"] and p["roles"][0]["role"] == "writer"
            # 前端判据：roles.length > 0 即认为有画像
            assert len(p["roles"]) > 0
    finally:
        _reset()


def test_profiles_isolated_per_user():
    """不同登录用户的画像不互通（P0-2 修复的延续）。"""
    from app.auth import create_jwt
    from app.auth.schemas import GitHubUser

    a = {"Authorization": f"Bearer {create_jwt(GitHubUser(id=21, login='diag_a', name='a'))}"}
    b = {"Authorization": f"Bearer {create_jwt(GitHubUser(id=22, login='diag_b', name='b'))}"}
    try:
        with TestClient(app) as c:
            c.post("/api/profile/diagnose", json={"role": "writer"}, headers=a)
            c.post("/api/profile/diagnose", json={"role": "modeler"}, headers=b)
            ra = c.get("/api/profile", headers=a).json()["profile"]
            rb = c.get("/api/profile", headers=b).json()["profile"]
            assert ra["roles"][0]["role"] == "writer"
            assert rb["roles"][0]["role"] == "modeler"
    finally:
        _profiles.pop("diag_a", None)
        _profiles.pop("diag_b", None)
