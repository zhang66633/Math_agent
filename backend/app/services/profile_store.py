"""用户画像持久化 — SQLite(重启不丢)。

背景：画像原先住在 `profile_routes._profiles` 这个**进程内存字典**里，重启即失，
且从未有人写入（审计 2026-10-14 第 11.2 节）。角色切换器接入后，画像成了首页
「继续学习」卡的判据，就必须落库。

存储选择：整条 UserProfile 序列化成 JSON 存一列。理由——画像是一次性读写整个
对象的文档型数据（roles/goal/self_assessment/calibrated_skills 嵌套且常变），
按字段拆表只会得到一堆单列表 + 频繁 migration；JSON 列保留 pydantic 校验在
模型层，DB 只负责耐久。user_id 是主键，读写都是一行。

库文件与 learning.db 相同：画像属于学习系统域，没必要为一张表单开一个文件。

连接管理（threading.local + WAL）用 services/storage.py 的 SqliteRepo 基类。
"""

from __future__ import annotations

import json

from ..learning.schemas import UserProfile
from .storage import SqliteRepo, utcnow


class ProfileStore(SqliteRepo):
    """用户画像持久化存储（user_id → UserProfile JSON）。"""

    SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profiles (
    user_id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

    def get(self, user_id: str) -> UserProfile | None:
        """读取画像；不存在返回 None。损坏行不炸服务，告警后按不存在处理。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT profile_json FROM profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return None
        try:
            return UserProfile(**json.loads(row["profile_json"]))
        except Exception:
            # 单行损坏不该让整个画像功能不可用：按「没有画像」处理，下次写入覆盖
            import logging

            logging.getLogger(__name__).warning("画像行损坏，按不存在处理: %s", user_id)
            return None

    def save(self, profile: UserProfile) -> None:
        """整对象 upsert；updated_at 以入库时间为准（模型里的值可能是旧的）。"""
        data = profile.model_dump(mode="json")
        now = utcnow()
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO profiles(user_id, profile_json, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(user_id) DO UPDATE SET"
                    "   profile_json = excluded.profile_json,"
                    "   updated_at = excluded.updated_at",
                    (
                        profile.user_id,
                        json.dumps(data, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                conn.commit()

    def delete(self, user_id: str) -> bool:
        """删除画像（测试清理用）。"""
        with self._lock:
            with self._get_conn() as conn:
                cur = conn.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))
                conn.commit()
                return cur.rowcount > 0


_store: ProfileStore | None = None


def get_profile_store() -> ProfileStore:
    """全局单例，DB 位于项目 data/learning.db（与学习事件同库）。"""
    global _store
    if _store is None:
        from ..config import get_settings

        settings = get_settings()
        _store = ProfileStore(db_path=settings.project_root / "data" / "learning.db")
    return _store


def set_profile_store(store: ProfileStore | None) -> None:
    """替换全局单例——测试注入临时库用，避免污染真实 learning.db。"""
    global _store
    _store = store
