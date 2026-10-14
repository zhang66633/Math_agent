"""用户画像 API — 角色选择、水平诊断、进度查询."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import GitHubUser, get_current_user, resolve_user_id
from ..learning.schemas import (
    AgentRole,
    LearningGoal,
    RoleProfile,
    SelfAssessment,
    UserProfile,
)
from ..services.profile_store import get_profile_store

profile_router = APIRouter(prefix="/profile", tags=["Profile"])


# ── 请求/响应模型 ─────────────────────────────────────


class DiagnoseRequest(BaseModel):
    role: str = "modeler"
    self_assessment: dict | None = (
        None  # {math_level, programming_level, writing_level, modeling_experience}
    )
    # goal / weekly_hours 传 None 表示「保留现值」。角色切换器每次切角色都会调本
    # 端点，若每次都拿默认值覆盖，用户在一次完整诊断里填下的目标就被冲掉了
    # （审计 2026-10-14 第 11.2 节：画像此前根本没有写入口，切换器接入时不能
    #  顺手引入另一个「重复调用即丢数据」的坑）。
    goal: str | None = None
    weekly_hours: int | None = None


class ProfileResponse(BaseModel):
    profile: UserProfile


# ── 存储 ──────────────────────────────────────────────────
# 画像落 SQLite（data/learning.db 的 profiles 表）。此前是进程内存字典
# `_profiles`——重启即失，且角色切换器接入后画像成了首页「继续学习」卡的判据，
# 不能再放内存里（审计 2026-10-14 第 11.2 节）。


def _get_or_create(user_id: str) -> UserProfile:
    store = get_profile_store()
    profile = store.get(user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id)
        store.save(profile)
    return profile


def _uid(user: GitHubUser | None) -> str:
    """数据归属 id——只从登录态来。

    审计 2026-10 P0-2：此前本文件把 user_id 硬编码成 "default"（还挂着
    「TODO: 后续对接 auth」），导致所有人的画像、进度、成就全混在一桶里。
    """
    return resolve_user_id(user)


# ── 路由 ─────────────────────────────────────────────


@profile_router.post("/diagnose", response_model=ProfileResponse)
async def diagnose(
    req: DiagnoseRequest,
    user: GitHubUser | None = Depends(get_current_user),
):
    """初始诊断: 选择角色 + 水平自评.

    语义是**合并**而非覆盖：role 必给（切换主角色）；goal / weekly_hours /
    self_assessment 不提供就保留画像里的现值。这样同一端点既能当一次性入职诊断
    用，也能被角色切换器反复调用而不会冲掉用户已填的目标。
    """
    profile = _get_or_create(_uid(user))

    try:
        role = AgentRole(req.role)
    except ValueError:
        role = AgentRole.MODELER

    # 设置主角色
    profile.roles = [RoleProfile(role=role, is_primary=True)]
    # 目标：只在调用方显式提供时更新，逐字段保留
    if req.goal is not None or req.weekly_hours is not None:
        profile.goal = LearningGoal(
            competition=req.goal or profile.goal.competition,
            weekly_hours=(
                req.weekly_hours
                if req.weekly_hours is not None
                else profile.goal.weekly_hours
            ),
        )

    if req.self_assessment:
        profile.self_assessment = SelfAssessment(**req.self_assessment)

    profile.updated_at = datetime.now()
    # 落库：画像已是 SQLite 持久对象，改完必须显式保存（内存字典时代靠引用突变）
    get_profile_store().save(profile)
    return ProfileResponse(profile=profile)


@profile_router.get("", response_model=ProfileResponse)
async def get_profile(user: GitHubUser | None = Depends(get_current_user)):
    """获取当前用户画像."""
    profile = _get_or_create(_uid(user))
    return ProfileResponse(profile=profile)


@profile_router.get("/progress", response_model=dict)
async def get_progress(user: GitHubUser | None = Depends(get_current_user)):
    """成长档案数据: 统计大屏/日历热力图/勋章墙(带进度)/待复习/角色掌握度。"""
    from ..learning.mastery_tracker import get_mastery_tracker
    from ..learning.unit_content import ALL_UNITS
    from ..services.achievement_service import get_achievement_service
    from ..services.learning_store import get_learning_store
    from ..services.practice_store import get_practice_store

    uid = _uid(user)
    tracker = get_mastery_tracker()
    achievement_service = get_achievement_service()
    lstore = get_learning_store()
    pstore = get_practice_store()

    # 掌握度恢复: 事件重放到 tracker(重启不丢)
    _replay_events_to_tracker(tracker, uid)

    # 应用艾宾浩斯遗忘衰减
    needs_review = tracker.apply_decay(uid)

    # 角色掌握度(修 bug: 传各角色真实 skill 集合而非空列表)
    role_skill_ids: dict[str, list[str]] = {"modeler": [], "programmer": [], "writer": []}
    for role, units in ALL_UNITS.items():
        for u in units:
            role_skill_ids[role].append(u.unit_id)

    # 统计
    pstats = pstore.get_stats(uid)
    persisted_events = lstore.list_events(uid)
    completed_units = len({r["unit_id"] for r in persisted_events if r["event_type"] == "learn"})
    streak_days = _calc_streak_dates(pstore.active_dates(uid) | lstore.active_dates(uid))
    achievements = achievement_service.check_all(uid)
    unlocked_count = sum(1 for a in achievements if a["unlocked"])

    return {
        "stats": {
            "total_units": sum(len(v) for v in ALL_UNITS.values()),  # 61
            "completed_units": completed_units,
            "streak_days": streak_days,
            "total_answers": pstats["total_answers"],
            "correct_answers": pstats["correct_answers"],
            "accuracy": round(pstats["correct_answers"] / pstats["total_answers"] * 100, 1)
            if pstats["total_answers"]
            else 0,
            "wrong_questions": pstats["wrong_questions"],
            "mastered_questions": pstats["mastered_questions"],
            "unlocked_achievements": unlocked_count,
            "total_achievements": len(achievements),
        },
        "calendar": _build_calendar(pstore.active_dates(uid) | lstore.active_dates(uid)),
        "achievements": achievements,
        "needs_review": [
            {"skill_id": sid, "retention": round(ret, 2)}
            for sid, ret in sorted(needs_review.items(), key=lambda x: x[1])[:8]
        ],
        "roles": {
            "modeler": round(tracker.get_role_overall(uid, role_skill_ids["modeler"]), 2),
            "programmer": round(
                tracker.get_role_overall(uid, role_skill_ids["programmer"]), 2
            ),
            "writer": round(tracker.get_role_overall(uid, role_skill_ids["writer"]), 2),
        },
        "weekly": _weekly_message(
            streak_days=streak_days,
            total_answers=pstats["total_answers"],
            wrong_questions=pstats["wrong_questions"],
            new_achievements=[a for a in achievements if a["is_new"]],
        ),
    }


@profile_router.post("/achievements/ack")
async def ack_achievements(user: GitHubUser | None = Depends(get_current_user)):
    """成就已读(前端庆祝弹窗关闭后调用,消 NEW 角标)。"""
    from ..services.achievement_service import get_achievement_service

    get_achievement_service().ack_all(_uid(user))
    return {"status": "ok"}


def _parse_naive_dt(iso: str):
    """ISO 字符串 → naive datetime(与 tracker 内部 datetime.utcnow() 约定一致)。"""
    from datetime import datetime

    return datetime.fromisoformat(iso).replace(tzinfo=None)


def _replay_events_to_tracker(tracker, user_id: str) -> None:
    """把持久层事件重放到掌握度追踪器(进程内幂等: 防同事件重复抬峰值)。

    user_id: 归属 id，由调用方从登录态解析（勿再用硬编码 "default"）。

    来源二: ①learning_events(事件钩子落库)②practice_records(历史作答,
    事件钩子上线前的练习也能恢复掌握度)。
    """
    from ..learning.schemas import LearningEvent
    from ..services.learning_store import get_learning_store
    from ..services.practice_store import get_practice_store

    replayed = getattr(tracker, "_replayed_ids", None)
    if replayed is None:
        replayed = set()
        tracker._replayed_ids = replayed

    for row in get_learning_store().list_events(user_id):
        if row["event_type"] == "practice":
            continue  # 练习掌握度统一从 practice_records 重放,避免双计
        if row["id"] in replayed:
            continue
        replayed.add(row["id"])
        tracker.update_from_event(
            user_id,
            LearningEvent(
                event_id=f"replay_{row['id']}",
                user_id=user_id,
                unit_id=row["unit_id"],
                skill_ids=[row["unit_id"]],
                event_type=row["event_type"],
                score=row["score"],
                created_at=_parse_naive_dt(row["created_at"]),
            ),
        )

    from ..learning.quiz_bank import get_question

    for row in get_practice_store().list_records(user_id):
        key = f"pr_{row['id']}"
        if key in replayed:
            continue
        replayed.add(key)
        # skill 以单元为准(与角色掌握度列表对齐),题目反查单元
        q = get_question(row["question_id"])
        unit_id = q["unit_id"] if q else row["question_id"]
        tracker.update_from_event(
            user_id,
            LearningEvent(
                event_id=key,
                user_id=user_id,
                unit_id=unit_id,
                skill_ids=[unit_id],
                event_type="practice",
                score=1.0 if row["is_correct"] else 0.0,
                created_at=_parse_naive_dt(row["created_at"]),
            ),
        )


def _calc_streak_dates(dates: set[str]) -> int:
    """连续学习天数(从最近活跃日往前数,今天未学习允许断档)。"""
    if not dates:
        return 0
    from datetime import datetime

    ordered = sorted(dates, reverse=True)
    streak = 1
    for i in range(1, len(ordered)):
        if (datetime.fromisoformat(ordered[i - 1]) - datetime.fromisoformat(ordered[i])).days == 1:
            streak += 1
        else:
            break
    return streak


def _build_calendar(active_dates: set[str]) -> list[dict]:
    """近 12 周每日活跃计数(GitHub 热力图数据: 无活动=count 0 也返回)。"""
    from datetime import datetime, timedelta

    today = datetime.now().date()
    # 对齐到本周一(周一为一周起点), 覆盖前 11 周 + 本周
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=11)
    result = []
    for i in range(84):  # 12 周 × 7 天
        d = start + timedelta(days=i)
        result.append(
            {
                "date": d.isoformat(),
                "count": 1 if d.isoformat() in active_dates else 0,
            }
        )
    return result


def _weekly_message(
    streak_days: int,
    total_answers: int,
    wrong_questions: int,
    new_achievements: list[dict],
) -> dict:
    """管家周播报(人格化文案,后端拼好;单元打卡已移除,不再提及完成单元)。"""
    parts = []
    if streak_days > 0:
        parts.append(f"已经连续学习 {streak_days} 天")
    if total_answers > 0:
        parts.append(f"累计刷了 {total_answers} 道题")
    if new_achievements:
        parts.append(f"新解锁 {len(new_achievements)} 枚勋章 🎉")
    elif wrong_questions > 0:
        parts.append(f"错题本里有 {wrong_questions} 道题等着你征服")
    if not parts:
        return {"message": "新的旅程从今天开始,去学习工位或训练场迈出第一步吧!"}
    return {"message": "管家播报:" + ",".join(parts) + "。"}
