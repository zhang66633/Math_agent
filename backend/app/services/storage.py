"""SQLite 存储基类 — SqliteSessionStore / LearningStore / PracticeStore 共用。

这三个 store 各自复制过一份连接管理样板（threading.local 每线程单连接 +
WAL + row_factory），并且已经漂移：session store 开了 `foreign_keys=ON`，
另两个没有。收敛到本基类后，差异只剩 SCHEMA_SQL 与两个钩子：

- `_migrate(conn)`：executescript 之前的轻量迁移（如补列）
- `_post_init(conn)`：executescript 之后的收尾（如历史数据回填）

线程模型：每线程一个复用连接（sqlite3 对象不能跨线程共享）；
写操作由子类自行用 `self._lock` 串行化（保持各 store 原有粒度）。
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path


def utcnow() -> str:
    """UTC ISO 时间戳（三个 store 各写过一份 _now/_utcnow，收敛到这里）。"""
    return datetime.now(UTC).isoformat()


class SqliteRepo:
    """SQLite 存储基类：子类声明 SCHEMA_SQL，按需覆盖 _migrate/_post_init。"""

    SCHEMA_SQL: str = ""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._local = threading.local()  # 每线程单连接复用（见 _get_conn）
        self._init_db()

    # ── 连接管理（三 store 共用的唯一实现）────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """每线程独立连接（复用，不每次新建）；启用 WAL + 外键。"""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        """关闭当前线程的连接（进程退出前调用）。"""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None

    # ── 建库（钩子供子类扩展）────────────────────────────────────

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self._get_conn() as conn:
                self._migrate(conn)
                if self.SCHEMA_SQL:
                    conn.executescript(self.SCHEMA_SQL)
                conn.commit()
                self._post_init(conn)
                conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """executescript 之前的轻量迁移（补列等）；默认无操作。"""

    def _post_init(self, conn: sqlite3.Connection) -> None:
        """executescript 之后的收尾（历史数据回填等）；默认无操作。"""
