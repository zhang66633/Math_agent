"""练习记录与错题本存储 — SQLite 持久化(重启不清零)。

连接管理用 services/storage.py 的 SqliteRepo 基类（threading.local
每线程连接 + WAL）；本文件的 _migrate/_post_init 保留旧库 round_id
补列与错题本回填两步初始化逻辑。
表 practice_records: 每次作答一条记录,错题以「同题最新一次作答正确」判定掌握。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .storage import SqliteRepo, utcnow


class PracticeStore(SqliteRepo):
    """选择题作答记录/错题本存储。"""

    SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS practice_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    question_id TEXT NOT NULL,
    choice INTEGER NOT NULL,
    is_correct INTEGER NOT NULL,
    round_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_practice_user_qid
    ON practice_records(user_id, question_id, created_at);
CREATE INDEX IF NOT EXISTS idx_practice_round
    ON practice_records(user_id, round_id);
CREATE TABLE IF NOT EXISTS mistake_book (
    user_id TEXT NOT NULL DEFAULT 'default',
    question_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, question_id)
);
"""

    def _migrate(self, conn: sqlite3.Connection) -> None:
        # 轻量迁移先行: 旧库缺 round_id 列(必须先于 SCHEMA_SQL, 其索引引用该列)
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(practice_records)")]
        except sqlite3.OperationalError:
            cols = []  # 表还不存在, SCHEMA_SQL 会建
        if cols and "round_id" not in cols:
            conn.execute(
                "ALTER TABLE practice_records ADD COLUMN round_id TEXT NOT NULL DEFAULT ''"
            )
            conn.commit()

    def _post_init(self, conn: sqlite3.Connection) -> None:
        # 错题本回填: 按历史记录最新状态(仅对空错题本生效, 幂等)
        n = conn.execute("SELECT COUNT(*) AS n FROM mistake_book").fetchone()["n"]
        if n == 0:
            for qid, is_correct in self._latest_states(conn):
                if not is_correct:
                    conn.execute(
                        "INSERT OR IGNORE INTO mistake_book(user_id, question_id, added_at)"
                        " VALUES ('default', ?, ?)",
                        (qid, utcnow()),
                    )
            conn.commit()

    @staticmethod
    def _latest_states(conn: sqlite3.Connection) -> list[tuple[str, bool]]:
        rows = conn.execute(
            "SELECT question_id, is_correct FROM practice_records ORDER BY id DESC"
        ).fetchall()
        latest: dict[str, bool] = {}
        for row in rows:
            latest.setdefault(row["question_id"], bool(row["is_correct"]))
        return list(latest.items())

    # ── 记录 ─────────────────────────────────────────────

    def record_answer(
        self,
        question_id: str,
        choice: int,
        is_correct: bool,
        user_id: str = "default",
        round_id: str = "",
        created_at: str | None = None,
    ) -> int:
        """记录一次作答并更新错题本;返回记录 id(供事件重放去重)。"""
        with self._lock:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "INSERT INTO practice_records"
                    "(user_id, question_id, choice, is_correct, round_id, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        question_id,
                        choice,
                        int(is_correct),
                        round_id,
                        created_at or utcnow(),
                    ),
                )
                row_id = int(cur.lastrowid)
                # 错题本状态转移: 答错入本, 答对出本(自动掌握)
                if is_correct:
                    conn.execute(
                        "DELETE FROM mistake_book WHERE user_id = ? AND question_id = ?",
                        (user_id, question_id),
                    )
                else:
                    conn.execute(
                        "INSERT OR IGNORE INTO mistake_book(user_id, question_id, added_at)"
                        " VALUES (?, ?, ?)",
                        (user_id, question_id, utcnow()),
                    )
                conn.commit()
                return row_id

    def discard_round(self, round_id: str, user_id: str = "default") -> int:
        """丢弃一轮练习的全部记录,并重算涉及题目的错题本状态。"""
        with self._lock:
            with self._get_conn() as conn:
                involved = [
                    r["question_id"]
                    for r in conn.execute(
                        "SELECT DISTINCT question_id FROM practice_records"
                        " WHERE user_id = ? AND round_id = ?",
                        (user_id, round_id),
                    ).fetchall()
                ]
                cur = conn.execute(
                    "DELETE FROM practice_records WHERE user_id = ? AND round_id = ?",
                    (user_id, round_id),
                )
                deleted = cur.rowcount
                # 重算: 剩余记录最新状态决定去留
                for qid in involved:
                    rows = conn.execute(
                        "SELECT is_correct FROM practice_records"
                        " WHERE user_id = ? AND question_id = ?"
                        " ORDER BY id DESC LIMIT 1",
                        (user_id, qid),
                    ).fetchall()
                    if not rows or bool(rows[0]["is_correct"]):
                        conn.execute(
                            "DELETE FROM mistake_book WHERE user_id = ? AND question_id = ?",
                            (user_id, qid),
                        )
                    else:
                        conn.execute(
                            "INSERT OR IGNORE INTO mistake_book(user_id, question_id, added_at)"
                            " VALUES (?, ?, ?)",
                            (user_id, qid, utcnow()),
                        )
                conn.commit()
                return deleted

    # ── 错题本 ───────────────────────────────────────────

    def add_to_mistake_book(self, question_id: str, user_id: str = "default") -> None:
        """手动加入错题本(幂等)。"""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO mistake_book(user_id, question_id, added_at)"
                    " VALUES (?, ?, ?)",
                    (user_id, question_id, utcnow()),
                )
                conn.commit()

    def remove_from_mistake_book(self, question_id: str, user_id: str = "default") -> None:
        """手动移出错题本。"""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "DELETE FROM mistake_book WHERE user_id = ? AND question_id = ?",
                    (user_id, question_id),
                )
                conn.commit()

    def get_wrong_question_ids(self, user_id: str = "default") -> set[str]:
        """错题本题目集合(答错自动入本 + 手动加入,答对/手动移除/丢弃轮次出本)。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT question_id FROM mistake_book WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {r["question_id"] for r in rows}

    def get_mistake_detail(
        self, question_id: str, user_id: str = "default"
    ) -> dict[str, Any] | None:
        """某题的错题详情(最后一次错误作答)。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT choice, is_correct, created_at FROM practice_records"
                " WHERE user_id = ? AND question_id = ? AND is_correct = 0"
                " ORDER BY id DESC LIMIT 1",
                (user_id, question_id),
            ).fetchone()
        return dict(row) if row else None

    def get_wrong_count(self, question_id: str, user_id: str = "default") -> int:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM practice_records"
                " WHERE user_id = ? AND question_id = ? AND is_correct = 0",
                (user_id, question_id),
            ).fetchone()
        return int(row["n"])

    def get_correct_count(self, question_id: str, user_id: str = "default") -> int:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM practice_records"
                " WHERE user_id = ? AND question_id = ? AND is_correct = 1",
                (user_id, question_id),
            ).fetchone()
        return int(row["n"])

    def get_wrong_counts(self, user_id: str = "default") -> dict[str, int]:
        """每道题的累计错误次数(一次查询,供题库列表批量标注)。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT question_id, COUNT(*) AS n FROM practice_records"
                " WHERE user_id = ? AND is_correct = 0"
                " GROUP BY question_id",
                (user_id,),
            ).fetchall()
        return {r["question_id"]: int(r["n"]) for r in rows}

    def get_tried_ids(self, user_id: str = "default") -> set[str]:
        """作答过的全部题目 id。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT question_id FROM practice_records WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {r["question_id"] for r in rows}

    def list_records(self, user_id: str = "default") -> list[dict]:
        """全部作答记录(按时间正序,供事件重放)。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM practice_records WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def active_dates(self, user_id: str = "default") -> set[str]:
        """有作答记录的日期集合(YYYY-MM-DD,供热力图/连续天数)。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT substr(created_at, 1, 10) AS d"
                " FROM practice_records WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {r["d"] for r in rows}

    def get_correct_categories(self, user_id: str = "default") -> int:
        """答对过题目的不同类别数(经 quiz_bank 反查)。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT question_id FROM practice_records"
                " WHERE user_id = ? AND is_correct = 1",
                (user_id,),
            ).fetchall()
        from ..learning.quiz_bank import get_question

        cats = set()
        for r in rows:
            q = get_question(r["question_id"])
            if q:
                cats.add(q["category"])
        return len(cats)

    def get_max_round_streak(self, user_id: str = "default") -> int:
        """单轮练习内最大连对数(按 round_id 分组,按作答顺序)。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT round_id, is_correct FROM practice_records"
                " WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()
        best = 0
        cur = 0
        prev_round = object()
        for r in rows:
            if r["round_id"] != prev_round:
                cur = 0
                prev_round = r["round_id"]
            if r["is_correct"]:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    def get_fixed_mistake_count(self, user_id: str = "default") -> int:
        """订正错题数: 先答错、之后又答对的不同题目数。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT question_id, is_correct FROM practice_records"
                " WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()
        wrong_seen: set[str] = set()
        fixed: set[str] = set()
        for r in rows:
            if r["is_correct"]:
                if r["question_id"] in wrong_seen:
                    fixed.add(r["question_id"])
            else:
                wrong_seen.add(r["question_id"])
        return len(fixed)

    def get_stats(self, user_id: str = "default") -> dict[str, Any]:
        """统计: 总作答次数 / 作对次数 / 错题数 / 已掌握题数。"""
        with self._get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM practice_records WHERE user_id = ?",
                (user_id,),
            ).fetchone()["n"]
            correct = conn.execute(
                "SELECT COUNT(*) AS n FROM practice_records WHERE user_id = ? AND is_correct = 1",
                (user_id,),
            ).fetchone()["n"]
        wrong_ids = self.get_wrong_question_ids(user_id)
        tried_ids: set[str] = set()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT question_id FROM practice_records WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            tried_ids = {r["question_id"] for r in rows}
        return {
            "total_answers": total,
            "correct_answers": correct,
            "wrong_questions": len(wrong_ids),
            "mastered_questions": len(tried_ids - wrong_ids),
        }


_store: PracticeStore | None = None


def get_practice_store() -> PracticeStore:
    """全局单例,DB 位于项目 data/ 目录。"""
    global _store
    if _store is None:
        from ..config import get_settings

        settings = get_settings()
        db_path = settings.project_root / "data" / "practice.db"
        _store = PracticeStore(db_path=db_path)
    return _store
