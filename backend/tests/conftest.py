"""pytest 共享配置。

存在原因：CI 上没有 `backend/.env`（被 .gitignore），而 `app.main` 的 lifespan 在
`jwt_secret` 为默认值 `"set-in-env-file"` 且 `debug=False` 时会直接 RuntimeError。
此前没有任何测试启动过 FastAPI app 所以没暴露；`tests/test_user_isolation.py`
用 TestClient 走真实 HTTP 后立刻炸了（2026-10 CI 实测 9 个失败）。

这里用一个 autouse fixture 保证测试进程内总有一个可用 secret，**让测试不再依赖
被 gitignore 的文件**。它只改内存中的单例，不写盘、不影响生产启动路径的强校验。
"""

import pytest

from app.config import get_settings
from app.services.profile_store import ProfileStore, set_profile_store

# 仅测试用。生产仍必须在 .env 配置 JWT_SECRET——lifespan 的强校验保持不变。
_TEST_JWT_SECRET = "pytest-only-secret-do-not-use-in-production"


@pytest.fixture(autouse=True)
def _ensure_jwt_secret_for_lifespan():
    settings = get_settings()
    if settings.jwt_secret == "set-in-env-file":
        settings.jwt_secret = _TEST_JWT_SECRET
    yield


@pytest.fixture(autouse=True)
def _isolate_profile_store(tmp_path):
    """把画像存储指到临时库，避免测试写进真实 data/learning.db。

    画像在 2026-10-14 从进程内存字典改成 SQLite 持久化（审计 11.2 节），
    于是「走真实 HTTP 的测试」开始会往真实库写画像行（test_user_isolation 的
    audit_owner_a/b 等）。单例是懒加载的，这里在测试前先注入一个临时库实例，
    测试结束后还原，生产路径不受影响。
    """
    set_profile_store(ProfileStore(db_path=tmp_path / "test_profile.db"))
    yield
    set_profile_store(None)
