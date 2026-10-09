"""学习事件与成就持久化 — SQLite(重启不丢)。

learning_events: 学习事件唯一事实源(单元完成/练习作答),成就、连续天数、
掌握度重放都从这里恢复。achievements: 成就解锁状态 + 未读标记。

连接管理（threading.local + WAL）用 services/storage.py 的 SqliteRepo 基类。
"""

from __future__ import annotations

from .storage import SqliteRepo, utcnow


class LearningStore(SqliteRepo):
    """学习事件与成就持久化存储。"""

    SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS learning_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    unit_id TEXT NOT NULL,
    event_type TEXT NOT NULL,      -- learn | practice
    score REAL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_user_time
    ON learning_events(user_id, created_at);
CREATE TABLE IF NOT EXISTS achievements (
    user_id TEXT NOT NULL DEFAULT 'default',
    achievement_id TEXT NOT NULL,
    unlocked_at TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, achievement_id)
);
"""

    # ── 学习事件 ────────────────────────────────────────

    def add_event(
        self,
        unit_id: str,
        event_type: str,
        score: float | None = None,
        user_id: str = "default",
        created_at: str | None = None,
    ) -> None:
        with self._lock:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "INSERT INTO learning_events(user_id, unit_id, event_type, score, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (user_id, unit_id, event_type, score, created_at or utcnow()),
                )
                conn.commit()
                # 返回行 id：调用方据此登记掌握度重放守卫，防双计（审查 P1）
                return cur.lastrowid

    def list_events(self, user_id: str = "default") -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM learning_events WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def active_dates(self, user_id: str = "default") -> set[str]:
        """有学习活动的日期集合(YYYY-MM-DD)。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT substr(created_at, 1, 10) AS d"
                " FROM learning_events WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {r["d"] for r in rows}

    def count_events(self, user_id: str = "default") -> int:
        with self._get_conn() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM learning_events WHERE user_id = ?",
                    (user_id,),
                ).fetchone()["n"]
            )

    # ── 成就 ────────────────────────────────────────────

    def unlock_achievement(self, achievement_id: str, user_id: str = "default") -> bool:
        """解锁成就(幂等);返回 True 表示本次新解锁。"""
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM achievements WHERE user_id = ? AND achievement_id = ?",
                    (user_id, achievement_id),
                ).fetchone()
                if row:
                    return False
                conn.execute(
                    "INSERT INTO achievements(user_id, achievement_id, unlocked_at, acknowledged)"
                    " VALUES (?, ?, ?, 0)",
                    (user_id, achievement_id, utcnow()),
                )
                conn.commit()
                return True

    def unlocked_ids(self, user_id: str = "default") -> dict[str, dict]:
        """已解锁成就: {achievement_id: {unlocked_at, acknowledged}}。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM achievements WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {
            r["achievement_id"]: {
                "unlocked_at": r["unlocked_at"],
                "acknowledged": bool(r["acknowledged"]),
            }
            for r in rows
        }

    def ack_all(self, user_id: str = "default") -> None:
        """全部成就标记已读(消未读)。"""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE achievements SET acknowledged = 1 WHERE user_id = ?",
                    (user_id,),
                )
                conn.commit()


_store: LearningStore | None = None


def get_learning_store() -> LearningStore:
    """全局单例,DB 位于项目 data/ 目录。"""
    global _store
    if _store is None:
        from ..config import get_settings

        settings = get_settings()
        _store = LearningStore(db_path=settings.project_root / "data" / "learning.db")
    return _store
