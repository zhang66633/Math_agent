"""Auth module — GitHub OAuth login + JWT session management."""

from .dependencies import (
    create_jwt,
    decode_jwt,
    get_current_user,
    require_auth,
    require_contributor,
)
from .github import ALLOWED_CONTRIBUTORS
from .schemas import GitHubUser, TokenResponse, UserResponse

# 未登录用户的共享桶。沿用历史值 "default"：learning/practice/profile/session
# 四处的存量数据都挂在它下面，改字面量会让老用户的数据全部「消失」。
GUEST_USER_ID = "default"


def resolve_user_id(user: GitHubUser | None, guest: str = GUEST_USER_ID) -> str:
    """把登录态解析成数据归属 id —— **唯一真源**。

    审计 2026-10 P0 的根因是同一件事在四个文件里各写了一遍、其中两处还写错：
      - session_routes 写对了（按 user.login 隔离）
      - tasks.py 注入了 user 却从不用 → 任务零隔离
      - learning_routes / profile_routes 直接把 user_id 当请求参数 → IDOR
    今后新增按用户隔离的数据，一律调本函数，不要再自己 `if user ... else`。
    """
    return user.login if (user and user.login) else guest


__all__ = [
    "GitHubUser",
    "TokenResponse",
    "UserResponse",
    "ALLOWED_CONTRIBUTORS",
    "GUEST_USER_ID",
    "create_jwt",
    "decode_jwt",
    "get_current_user",
    "require_auth",
    "require_contributor",
    "resolve_user_id",
]
