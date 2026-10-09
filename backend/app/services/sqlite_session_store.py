"""SQLite 会话存储 — 对话持久化 + 消息天的 CRUD 操作。

连接管理（threading.local + WAL）已收敛到 services/storage.py 的
SqliteRepo 基类，本文件只保留会话/消息的表结构与业务逻辑。
表结构：
  conversations: id, user_id, mode, title, created_at, updated_at
  messages:      id, conversation_id, msg_type, content, tool_name,
                 tool_input, tool_output, status, thinking,
                 agent_type, answered, created_at
"""

from __future__ import annotations

import json
import logging
import sqlite3

from app.config import get_settings

from .storage import SqliteRepo, utcnow

logger = logging.getLogger(__name__)


class SqliteSessionStore(SqliteRepo):
    """线程安全的 SQLite 会话存储。

    Usage:
        store = SqliteSessionStore(db_path=Path("data/sessions.db"))
        conv = store.create_conversation(mode="chat", title="新对话")
        store.add_message(conv_id, msg_dict)
        msgs = store.get_messages(conv_id)
    """

    SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default',
    mode        TEXT NOT NULL DEFAULT 'chat',
    title       TEXT NOT NULL DEFAULT '新对话',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT NOT NULL,
    msg_type          TEXT NOT NULL,
    content           TEXT,
    tool_name         TEXT,
    tool_input        TEXT,
    tool_output       TEXT,
    status            TEXT,
    thinking          TEXT,
    agent_type        TEXT,
    answered          INTEGER,
    streaming         INTEGER DEFAULT 0,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv
    ON messages(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_conversations_user_mode
    ON conversations(user_id, mode, updated_at DESC);
"""

    # ── 会话 CRUD ────────────────────────────────────────

    def create_conversation(
        self,
        user_id: str = "default",
        mode: str = "chat",
        title: str = "新对话",
        conv_id: str | None = None,
    ) -> dict:
        """创建新会话，返回会话 dict。支持客户端指定 id(幂等: 已存在则返回现有)。"""
        import uuid

        if conv_id:
            existing = self.get_conversation(conv_id, user_id=user_id)
            if existing:
                return existing
        conv_id = conv_id or f"conv_{uuid.uuid4().hex[:12]}"
        now = utcnow()
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO conversations (id, user_id, mode, title, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (conv_id, user_id, mode, title, now, now),
                )
                conn.commit()
        return {
            "id": conv_id,
            "user_id": user_id,
            "mode": mode,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }

    def list_conversations(
        self,
        user_id: str = "default",
        mode: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """列出会话列表，按更新时间倒序。"""
        with self._lock:
            with self._get_conn() as conn:
                if mode:
                    rows = conn.execute(
                        "SELECT * FROM conversations "
                        "WHERE user_id = ? AND mode = ? "
                        "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                        (user_id, mode, limit, offset),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM conversations "
                        "WHERE user_id = ? "
                        "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                        (user_id, limit, offset),
                    ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: str, user_id: str | None = None) -> dict | None:
        """获取单个会话；提供 user_id 时校验属主（不匹配视为不存在）。"""
        with self._lock:
            with self._get_conn() as conn:
                if user_id is not None:
                    row = conn.execute(
                        "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                        (conv_id, user_id),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
                    ).fetchone()
        return dict(row) if row else None

    def update_conversation(
        self, conv_id: str, user_id: str | None = None, **fields
    ) -> dict | None:
        """更新会话字段（title, mode 等）；提供 user_id 时校验属主。"""
        allowed = {"title", "mode", "updated_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_conversation(conv_id, user_id=user_id)
        updates["updated_at"] = utcnow()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [conv_id]
        where = "id = ?" if user_id is None else "id = ? AND user_id = ?"
        if user_id is not None:
            values.append(user_id)

        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    f"UPDATE conversations SET {set_clause} WHERE {where}",
                    values,
                )
                conn.commit()
        return self.get_conversation(conv_id, user_id=user_id)

    def delete_conversation(self, conv_id: str, user_id: str | None = None) -> bool:
        """删除会话及其所有消息（CASCADE）；提供 user_id 时校验属主。"""
        with self._lock:
            with self._get_conn() as conn:
                if user_id is not None:
                    cur = conn.execute(
                        "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                        (conv_id, user_id),
                    )
                else:
                    cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
                conn.commit()
                return cur.rowcount > 0

    # ── 消息 CRUD ────────────────────────────────────────

    def add_message(self, conv_id: str, msg: dict) -> dict | None:
        """追加一条消息。msg 需含 id, msg_type, created_at 字段。"""
        # 自动填充 created_at
        if "created_at" not in msg:
            msg["created_at"] = utcnow()

        with self._lock:
            with self._get_conn() as conn:
                try:
                    conn.execute(
                        """INSERT INTO messages
                           (id, conversation_id, msg_type, content, tool_name,
                            tool_input, tool_output, status, thinking,
                            agent_type, answered, streaming, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            msg["id"],
                            conv_id,
                            msg.get("msg_type", "agent"),
                            msg.get("content"),
                            msg.get("tool_name"),
                            json.dumps(msg.get("input")) if msg.get("input") else None,
                            json.dumps(msg.get("output")) if msg.get("output") else None,
                            msg.get("status"),
                            msg.get("thinking"),
                            msg.get("agent_type"),
                            1 if msg.get("answered") else 0,
                            1 if msg.get("streaming") else 0,
                            msg["created_at"],
                        ),
                    )
                    # 更新会话的 updated_at
                    conn.execute(
                        "UPDATE conversations SET updated_at = ? WHERE id = ?",
                        (utcnow(), conv_id),
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    logger.warning("消息 ID 重复: %s", msg.get("id"))
                    return None
        return msg

    def add_messages_batch(self, conv_id: str, msgs: list[dict]) -> int:
        """批量追加消息（用于同步完整的会话消息列表）。"""
        count = 0
        with self._lock:
            with self._get_conn() as conn:
                for msg in msgs:
                    if "created_at" not in msg:
                        msg["created_at"] = utcnow()
                    try:
                        conn.execute(
                            """INSERT OR REPLACE INTO messages
                               (id, conversation_id, msg_type, content, tool_name,
                                tool_input, tool_output, status, thinking,
                                agent_type, answered, streaming, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                msg["id"],
                                conv_id,
                                msg.get("msg_type", "agent"),
                                msg.get("content"),
                                msg.get("tool_name"),
                                json.dumps(msg.get("input")) if msg.get("input") else None,
                                json.dumps(msg.get("output")) if msg.get("output") else None,
                                msg.get("status"),
                                msg.get("thinking"),
                                msg.get("agent_type"),
                                1 if msg.get("answered") else 0,
                                1 if msg.get("streaming") else 0,
                                msg["created_at"],
                            ),
                        )
                        count += 1
                    except Exception:
                        logger.warning("批量插入消息失败: %s", msg.get("id"))
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (utcnow(), conv_id),
                )
                conn.commit()
        return count

    def get_messages(
        self,
        conv_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        """获取会话消息列表，按创建时间正序。"""
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE conversation_id = ? "
                    "ORDER BY created_at ASC LIMIT ? OFFSET ?",
                    (conv_id, limit, offset),
                ).fetchall()
        return [_deserialize_msg(r) for r in rows]

    def update_message(self, msg_id: str, **fields) -> dict | None:
        """更新单条消息字段（流式更新 content / status / thinking 等）。"""
        allowed = {
            "content",
            "tool_input",
            "tool_output",
            "status",
            "thinking",
            "answered",
            "streaming",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return None

        # 特殊处理 JSON 字段
        if "tool_input" in updates and updates["tool_input"] is not None:
            updates["tool_input"] = (
                json.dumps(updates["tool_input"])
                if not isinstance(updates["tool_input"], str)
                else updates["tool_input"]
            )
        if "tool_output" in updates and updates["tool_output"] is not None:
            updates["tool_output"] = (
                json.dumps(updates["tool_output"])
                if not isinstance(updates["tool_output"], str)
                else updates["tool_output"]
            )
        if "answered" in updates:
            updates["answered"] = 1 if updates["answered"] else 0
        if "streaming" in updates:
            updates["streaming"] = 1 if updates["streaming"] else 0

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [msg_id]

        with self._lock:
            with self._get_conn() as conn:
                conn.execute(f"UPDATE messages SET {set_clause} WHERE id = ?", values)
                conn.commit()
                row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        return _deserialize_msg(row) if row else None

    def delete_messages(self, conv_id: str) -> int:
        """删除会话下的所有消息。"""
        with self._lock:
            with self._get_conn() as conn:
                cur = conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
                conn.commit()
                return cur.rowcount

    # ── 统计 ────────────────────────────────────────────

    def count_conversations(self, user_id: str = "default") -> int:
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM conversations WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
        return row[0] if row else 0

    def count_messages(self, conv_id: str) -> int:
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                    (conv_id,),
                ).fetchone()
        return row[0] if row else 0


def _deserialize_msg(row: sqlite3.Row) -> dict:
    """将 SQLite Row 转为前端期望的消息格式。"""
    d = dict(row)
    # 反序列化 JSON 字段
    for field in ("tool_input", "tool_output"):
        if d.get(field) and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except json.JSONDecodeError:
                pass
    # 映射字段名
    if "tool_input" in d:
        d["input"] = d.pop("tool_input")
    if "tool_output" in d:
        d["output"] = d.pop("tool_output")
    # 布尔字段
    if "answered" in d:
        d["answered"] = bool(d["answered"])
    if "streaming" in d:
        d["streaming"] = bool(d["streaming"])
    return d


# ── 全局单例 ──────────────────────────────────────────

_store: SqliteSessionStore | None = None


def get_sqlite_store() -> SqliteSessionStore:
    """获取全局 SQLite 会话存储单例。"""
    global _store
    if _store is None:
        settings = get_settings()
        db_path = settings.project_root / "data" / "sessions.db"
        _store = SqliteSessionStore(db_path=db_path)
        logger.info("SQLite 会话存储已初始化: %s", db_path)
    return _store
