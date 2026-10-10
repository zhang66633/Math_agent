"""成就计算服务 — 10 项三档成就,带进度/目标,解锁状态持久化。

数据源: learning_store(学习事件)+ practice_store(作答流水/错题本),
全部 SQLite 持久化,重启不丢。check_all 判定后新解锁写入 achievements 表
(acknowledged=0 表示未读,前端弹彩带庆祝后调 ack)。

注: 单元打卡功能已移除,依赖 learn 事件的成就(学有所成/持之以恒)已删,
所有成就目标现均由训练场练习数据驱动。
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..learning.quiz_bank import get_question
from ..learning.schemas import LearningEvent

ACHIEVEMENT_DEFS = [
    # ── 铜 ──────────────────────────────────────────
    {
        "id": "first_practice",
        "name": "初出茅庐",
        "tier": "bronze",
        "desc": "完成第一次练习",
        "icon": "sprout",
        "check": "first_practice",
    },
    {
        "id": "quiz_10",
        "name": "小试牛刀",
        "tier": "bronze",
        "desc": "累计刷满 10 道题",
        "icon": "target",
        "check": "quiz_count_10",
    },
    {
        "id": "fix_3",
        "name": "知错能改",
        "tier": "bronze",
        "desc": "订正 3 道错题(重做答对)",
        "icon": "pencil",
        "check": "fix_3",
    },
    # ── 银 ──────────────────────────────────────────
    {
        "id": "quiz_100",
        "name": "刷题百斩",
        "tier": "silver",
        "desc": "累计刷满 100 道题",
        "icon": "swords",
        "check": "quiz_count_100",
    },
    {
        "id": "streak_7",
        "name": "坚持不懈",
        "tier": "silver",
        "desc": "连续学习 7 天",
        "icon": "flame",
        "check": "streak_7",
    },
    {
        "id": "categories_5",
        "name": "博采众长",
        "tier": "silver",
        "desc": "在 5 个不同类别中答对过题目",
        "icon": "compass",
        "check": "categories_5",
    },
    # ── 金 ──────────────────────────────────────────
    {
        "id": "quiz_300",
        "name": "题库战神",
        "tier": "gold",
        "desc": "累计刷满 300 道题",
        "icon": "trophy",
        "check": "quiz_count_300",
    },
    {
        "id": "streak_30",
        "name": "习惯养成",
        "tier": "gold",
        "desc": "连续学习 30 天",
        "icon": "mountain",
        "check": "streak_30",
    },
    {
        "id": "all_rounder",
        "name": "全能选手",
        "tier": "gold",
        "desc": "三个角色的题目都刷过",
        "icon": "star",
        "check": "all_rounder",
    },
    {
        "id": "perfect_10",
        "name": "十全十美",
        "tier": "gold",
        "desc": "单轮练习连续答对 10 题",
        "icon": "badge",
        "check": "perfect_10",
    },
]

_TARGETS = {
    "quiz_count_10": 10,
    "quiz_count_100": 100,
    "quiz_count_300": 300,
    "streak_7": 7,
    "streak_30": 30,
    "categories_5": 5,
    "all_rounder": 3,
    "perfect_10": 10,
    "fix_3": 3,
}


class AchievementService:
    """成就判定服务(数据读持久层,判定结果写回持久层)。"""

    def __init__(self):
        self._events: list[LearningEvent] = []

    # ── 事件(内存态,供 mastery/即时判定;持久层见 learning_store)──

    def load_events(self, user_id: str) -> None:
        """从持久层重放事件(重启恢复)。"""
        from .learning_store import get_learning_store

        for row in get_learning_store().list_events(user_id):
            self._events.append(
                LearningEvent(
                    event_id=f"replay_{row['id']}",
                    user_id=row["user_id"],
                    unit_id=row["unit_id"],
                    skill_ids=[row["unit_id"]],
                    event_type=row["event_type"],
                    score=row["score"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )

    def add_event(self, event: LearningEvent) -> None:
        self._events.append(event)

    # ── 判定 ───────────────────────────────────────────

    def check_all(self, user_id: str = "default") -> list[dict]:
        """全部成就: {id, name, desc, icon, tier, progress, target, unlocked, unlocked_at, is_new}。

        新解锁会写入持久层(acknowledged=0);is_new = 已解锁且未读。
        """
        from .learning_store import get_learning_store
        from .practice_store import get_practice_store

        store = get_learning_store()
        pstore = get_practice_store()

        # 数据快照(事实源: 持久层; self._events 仅为本进程增量, 已在持久层中)
        pstats = pstore.get_stats(user_id)
        persisted = store.list_events(user_id)
        practice_dates = pstore.active_dates(user_id)
        learn_dates = store.active_dates(user_id)
        all_dates = practice_dates | learn_dates
        streak = _calc_streak_dates(all_dates)

        def progress_of(check: str) -> int:
            if check == "first_practice":
                return (
                    1
                    if any(r["event_type"] == "practice" for r in persisted)
                    or pstats["total_answers"] > 0
                    else 0
                )
            if check in ("quiz_count_10", "quiz_count_100", "quiz_count_300"):
                return pstats["total_answers"]
            if check in ("streak_7", "streak_30"):
                return streak
            if check == "categories_5":
                return pstore.get_correct_categories(user_id)
            if check == "all_rounder":
                unit_ids = {r["unit_id"] for r in persisted}
                roles = {get_question(u)["role"] for u in unit_ids if get_question(u)}
                return len(roles)
            if check == "perfect_10":
                return pstore.get_max_round_streak(user_id)
            if check == "fix_3":
                return pstore.get_fixed_mistake_count(user_id)
            return 0

        results = []
        for ach in ACHIEVEMENT_DEFS:
            check = ach["check"]
            target = _TARGETS.get(check, 1)
            progress = min(progress_of(check), target)
            unlocked = progress >= target
            if unlocked:
                store.unlock_achievement(ach["id"], user_id)  # 幂等持久化
                # 解锁后重读元数据(本次新解锁 acknowledged=0 → is_new=True)
                meta = store.unlocked_ids(user_id).get(ach["id"], {})
            else:
                meta = {}
            results.append(
                {
                    "id": ach["id"],
                    "name": ach["name"],
                    "desc": ach["desc"],
                    "icon": ach["icon"],
                    "tier": ach["tier"],
                    "progress": progress,
                    "target": target,
                    "unlocked": unlocked,
                    "unlocked_at": meta.get("unlocked_at") if unlocked else None,
                    "is_new": unlocked and not meta.get("acknowledged", True),
                }
            )
        return results

    def ack_all(self, user_id: str = "default") -> None:
        from .learning_store import get_learning_store

        get_learning_store().ack_all(user_id)


def _calc_streak_dates(dates: set[str]) -> int:
    """从日期集合(YYYY-MM-DD)计算连续天数: 从今天或最近一天往前数。"""
    if not dates:
        return 0
    datetime.now(UTC).date().isoformat()
    ordered = sorted(dates, reverse=True)
    # 最近活动日不是今天 → 从最近一天起算(允许断档)
    streak = 1
    for i in range(1, len(ordered)):
        prev = datetime.fromisoformat(ordered[i - 1])
        cur = datetime.fromisoformat(ordered[i])
        if (prev - cur).days == 1:
            streak += 1
        else:
            break
    return streak


def _calc_streak(events: list[LearningEvent]) -> int:
    """基于事件计算连续学习天数(保留,供兼容)。"""
    dates = {e.created_at.date().isoformat() for e in events if e.created_at}
    return _calc_streak_dates(dates)


# ── 全局单例 ──────────────────────────────────────────

_service: AchievementService | None = None


def get_achievement_service() -> AchievementService:
    global _service
    if _service is None:
        _service = AchievementService()
        _service.load_events("default")  # 启动即重放历史事件
    return _service
