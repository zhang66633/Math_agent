"""WebSocket endpoints for real-time agent progress."""

import asyncio
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..auth import resolve_user_id
from ..auth.dependencies import decode_jwt
from ..config import get_settings
from ..services.redis_pubsub import RedisSubscriber
from ..services.session import get_session_manager

logger = logging.getLogger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws/task/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str, token: str = Query(default="")):
    """WebSocket endpoint for real-time task message streaming.

    Requires a valid JWT passed as ?token=<jwt> query parameter.
    Subscribes to Redis Pub/Sub channel ``task:{task_id}`` and forwards
    every published event to the connected frontend client.

    鉴权 + 属主校验（审计 2026-10 P0-1）：此前本端点只 decode 不校验，
    任何拿到 task_id 的人都能订阅他人任务的实时执行过程。现在按 token
    解析归属，与 REST 侧共用 resolve_user_id；访客仍放行（未登录 → guest
    桶），否则方案页对未登录用户会全程空白。
    """
    user = decode_jwt(token) if token else None
    uid = resolve_user_id(user)
    if not get_session_manager().get_owned(task_id, uid):
        # 未 accept 直接 close：对未授权方不泄露 task_id 是否存在
        await websocket.close(code=1008, reason="task not found or not yours")
        return

    await websocket.accept()
    settings = get_settings()

    # Send an initial connection-confirmation event
    await websocket.send_text(
        json.dumps(
            {
                "event": "connected",
                "task_id": task_id,
            },
            ensure_ascii=False,
        )
    )

    subscriber = RedisSubscriber(settings.redis_url)

    try:
        async for event_json in subscriber.subscribe(task_id):
            try:
                await websocket.send_text(event_json)
            except Exception:
                # Client disconnected — stop consuming
                break
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected for task %s", task_id)
    except asyncio.CancelledError:
        logger.info("WebSocket cancelled for task %s", task_id)
    except Exception:
        logger.exception("WebSocket error for task %s", task_id)
