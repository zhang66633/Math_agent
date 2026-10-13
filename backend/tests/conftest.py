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

# 仅测试用。生产仍必须在 .env 配置 JWT_SECRET——lifespan 的强校验保持不变。
_TEST_JWT_SECRET = "pytest-only-secret-do-not-use-in-production"


@pytest.fixture(autouse=True)
def _ensure_jwt_secret_for_lifespan():
    settings = get_settings()
    if settings.jwt_secret == "set-in-env-file":
        settings.jwt_secret = _TEST_JWT_SECRET
    yield
