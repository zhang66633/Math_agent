"""会话管理 REST API — 对话列表、消息同步、删除。

依赖于 SqliteSessionStore 进行持久化。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import GitHubUser, get_current_user, resolve_user_id
from ..services.sqlite_session_store import get_sqlite_store

logger = logging.getLogger(__name__)

session_router = APIRouter(prefix="/conversations", tags=["Conversations"])

# 访客共享桶（历史数据 user_id='default'，沿用该值保证旧会话可见）
GUEST_USER_ID = "default"


def _resolve_uid(user: GitHubUser | None) -> str:
    """登录用户按 GitHub login 隔离；访客落入共享桶。

    真源在 app.auth.resolve_user_id——这里保留薄封装只为不改动下方 8 个调用点。
    """
    return resolve_user_id(user, guest=GUEST_USER_ID)


# ── 请求/响应模型 ─────────────────────────────────────


class CreateConversationRequest(BaseModel):
    mode: str = "chat"  # chat | qa | practice | solution | learning
    title: str = "新对话"
    id: str | None = None  # 客户端会话 id(前端本地 id 与服务端对齐,幂等)


class UpdateConversationRequest(BaseModel):
    title: str | None = None


class MessagePayload(BaseModel):
    id: str
    msg_type: str
    content: str | None = None
    tool_name: str | None = None
    input: dict | None = None
    output: list | None = None
    status: str | None = None
    thinking: str | None = None
    agent_type: str | None = None
    answered: bool | None = None
    streaming: bool | None = None
    created_at: str | None = None


class SyncMessagesRequest(BaseModel):
    messages: list[MessagePayload]


# ── 路由 ─────────────────────────────────────────────


@session_router.get("")
async def list_conversations(
    mode: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: GitHubUser | None = Depends(get_current_user),
):
    """列出当前用户的会话列表，按更新时间倒序。"""
    store = get_sqlite_store()
    uid = _resolve_uid(user)
    convs = store.list_conversations(user_id=uid, mode=mode, limit=limit, offset=offset)
    return {
        "conversations": convs,
        "total": store.count_conversations(user_id=uid),
    }


@session_router.post("")
async def create_conversation(
    req: CreateConversationRequest,
    user: GitHubUser | None = Depends(get_current_user),
):
    """创建新会话（归属当前用户）。"""
    store = get_sqlite_store()
    conv = store.create_conversation(user_id=_resolve_uid(user), mode=req.mode, title=req.title, conv_id=req.id)
    return {"conversation": conv}


@session_router.get("/{conv_id}")
async def get_conversation(
    conv_id: str,
    user: GitHubUser | None = Depends(get_current_user),
):
    """获取单个会话详情（校验属主）。"""
    store = get_sqlite_store()
    conv = store.get_conversation(conv_id, user_id=_resolve_uid(user))
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"conversation": conv}


@session_router.patch("/{conv_id}")
async def update_conversation(
    conv_id: str,
    req: UpdateConversationRequest,
    user: GitHubUser | None = Depends(get_current_user),
):
    """更新会话标题（校验属主）。"""
    store = get_sqlite_store()
    updates = {}
    if req.title is not None:
        updates["title"] = req.title
    conv = store.update_conversation(conv_id, user_id=_resolve_uid(user), **updates)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"conversation": conv}


@session_router.delete("/{conv_id}")
async def delete_conversation(
    conv_id: str,
    user: GitHubUser | None = Depends(get_current_user),
):
    """删除会话及其所有消息（校验属主）。"""
    store = get_sqlite_store()
    ok = store.delete_conversation(conv_id, user_id=_resolve_uid(user))
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "ok"}


# ── 消息路由 ─────────────────────────────────────────


@session_router.get("/{conv_id}/messages")
async def get_messages(
    conv_id: str,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    user: GitHubUser | None = Depends(get_current_user),
):
    """获取会话消息列表（校验属主）。"""
    store = get_sqlite_store()
    conv = store.get_conversation(conv_id, user_id=_resolve_uid(user))
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = store.get_messages(conv_id, limit=limit, offset=offset)
    return {
        "messages": msgs,
        "total": store.count_messages(conv_id),
    }


@session_router.post("/{conv_id}/messages")
async def add_message(
    conv_id: str,
    msg: MessagePayload,
    user: GitHubUser | None = Depends(get_current_user),
):
    """追加一条消息到会话（校验属主）。"""
    store = get_sqlite_store()
    conv = store.get_conversation(conv_id, user_id=_resolve_uid(user))
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    result = store.add_message(conv_id, msg.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=409, detail="消息 ID 重复")
    return {"message": result}


@session_router.post("/{conv_id}/sync")
async def sync_messages(
    conv_id: str,
    req: SyncMessagesRequest,
    user: GitHubUser | None = Depends(get_current_user),
):
    """批量同步消息（用于前端 localStorage → 后端首次迁移；校验属主）。"""
    store = get_sqlite_store()
    conv = store.get_conversation(conv_id, user_id=_resolve_uid(user))
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    count = store.add_messages_batch(
        conv_id,
        [m.model_dump(exclude_none=True) for m in req.messages],
    )
    return {"synced": count}
