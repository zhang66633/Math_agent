"""沙箱安全不变量回归测试（审计 2026-10 P0 + CI 2026-10 修复）。

要守住的**不变量**（与用哪个后端无关）：
  ① 沙箱代码无法 import 后端源码（`app.*`）——否则可直读 .env 的 JWT_SECRET / API Key
  ② 沙箱代码无法访问网络
  ③ 科学计算栈（numpy/pandas/matplotlib/sympy）不被误伤

为什么断言不变量而不是机制：
  subprocess 模式靠 `_wrap_code` 的前置码（sys.path 剔除 + meta_path 屏蔽）；
  docker 模式靠「仓库根本不挂进容器 + --network=none」。两者机制不同但结论必须一致。
  2026-10 CI 第一次跑挂就是 because 测试写死了 subprocess 的错误文案，而 runner 上
  docker 可用（无镜像）走了另一条路。机制本身由下面几个不执行子进程的单测锁住。

运行: 在 backend/ 目录下 `python -m pytest tests/test_sandbox_source_isolation.py -q`
"""

import compileall
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.sandbox.executor import (  # noqa: E402
    SANDBOX_IMAGE,
    SandboxExecutor,
    docker_daemon_up,
    docker_image_ready,
)

_EXEC = SandboxExecutor(timeout=120)
_BACKEND = "docker" if (docker_daemon_up() and docker_image_ready()) else "subprocess"


def _run(code: str) -> dict:
    return _EXEC.run(code)


# ── 不变量（真实执行，后端无关）─────────────────────────


def test_import_backend_config_blocked():
    """import app.config 必须失败——这是泄露 .env 密钥的直接通道。"""
    r = _run("import app.config\nprint('LEAKED')")
    out = r.get("stdout") or ""
    err = r.get("stderr") or ""
    assert "LEAKED" not in out, f"沙箱仍能导入后端源码: {out}"
    # subprocess: 自定义 ImportError；docker: 容器里没装 app 包 → ModuleNotFoundError
    assert "沙箱禁止导入后端源码包" in err or "ModuleNotFoundError" in err, (
        f"未拿到预期的导入阻断信息: {err[:300]}"
    )


def test_import_backend_submodules_blocked():
    """app 的子包同样要挡住（app.core.nodes / app.api.apikeys / app.services.session）。"""
    for mod in ("app.core.nodes", "app.api.apikeys", "app.services.session"):
        r = _run(f"import {mod}\nprint('LEAKED')")
        assert "LEAKED" not in (r.get("stdout") or ""), f"{mod} 竟可导入"
        err = r.get("stderr") or ""
        assert "沙箱禁止导入后端源码包" in err or "ModuleNotFoundError" in err, (
            f"{mod} 未拿到预期的阻断信息: {err[:200]}"
        )


def test_backend_source_not_reachable_after_sys_path_reinjection():
    """即便用户代码把 backend/ 加回 sys.path，也 import 不到后端源码。"""
    backend_dir = str(Path(__file__).resolve().parent.parent)
    code = (
        "import sys\n"
        f"sys.path.append({backend_dir!r})\n"
        "import app.config\n"
        "print('LEAKED')\n"
    )
    r = _run(code)
    assert "LEAKED" not in (r.get("stdout") or ""), "sys.path 重新注入后仍可导入后端源码"
    err = r.get("stderr") or ""
    assert "沙箱禁止导入后端源码包" in err or "ModuleNotFoundError" in err, err[:200]


def test_project_root_not_on_sys_path():
    """sys.path 中不得残留仓库根 / backend/（.venv 需保留，科学计算栈装在里面）。"""
    repo_root = str(Path(__file__).resolve().parent.parent.parent)
    backend_dir = str(Path(__file__).resolve().parent.parent)
    code = (
        "import sys, os\n"
        f"forbidden = {[repo_root, backend_dir]!r}\n"
        "roots = [os.path.realpath(p or os.getcwd()) for p in sys.path]\n"
        "bad = [p for p in roots if p in forbidden]\n"
        "print('BAD=' + repr(bad))\n"
    )
    r = _run(code)
    out = r.get("stdout") or ""
    assert "BAD=[]" in out, f"sys.path 仍含仓库路径: {out}"


def test_network_still_blocked():
    """socket 出网必须被阻断（两种后端都拦，只是报错文案不同）。"""
    r = _run(
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 443), timeout=3)\n"
        "    print('NET_OPEN')\n"
        "except Exception as e:\n"
        "    print('NET_CLOSED', type(e).__name__)\n"
    )
    assert "NET_CLOSED" in (r.get("stdout") or ""), r.get("stdout")


def test_normal_scientific_stack_still_works():
    """回归护栏：修复不能误伤科学计算栈（numpy/pandas/matplotlib/sympy）。"""
    code = (
        "import numpy as np, pandas as pd, sympy as sp\n"
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3], [1, 4, 9]); plt.savefig('smoke.png')\n"
        "print('OK', float(np.mean([1, 2, 3])), pd.__name__, sp.Integer(2) * 3)\n"
    )
    r = _run(code)
    assert r.get("success"), f"科学计算栈被误伤: {(r.get('stderr') or '')[:400]}"
    assert "OK 2.0 pandas 6" in (r.get("stdout") or ""), r.get("stdout")
    assert r.get("images"), "matplotlib 图表未被捕获（按需配置回归）"


# ── 机制单测（不执行子进程，锁住 subprocess 前置码本身）────────


def test_wrap_code_contains_source_isolation_prelude():
    """_wrap_code 必须生成后端源码隔离前置码——这是 subprocess 模式的防线本体。"""
    with tempfile.TemporaryDirectory() as d:
        wrapped = SandboxExecutor()._wrap_code("print('hi')", d)

    assert "_BlockBackendSource" in wrapped, "缺少 meta_path 屏蔽 finder"
    assert "_SANDBOX_BLOCKED_TOPLEVEL" in wrapped, "缺少被屏蔽的顶层包集合"
    assert '"app"' in wrapped and '"math_model_agent"' in wrapped, "屏蔽集合内容不对"
    assert "_sys.path[:]" in wrapped, "缺少 sys.path 剔除"
    # json.dumps 会转义反斜杠，故比对转义后的形式（Windows 路径）
    expected_root = json.dumps(str(get_settings().project_root.parent))[1:-1]
    assert expected_root in wrapped, "未注入仓库根路径"


def test_wrap_code_output_is_valid_python():
    """生成的前置码必须能独立编译通过——f-string 转义写错会静默产出坏代码。"""
    with tempfile.TemporaryDirectory() as d:
        wrapped = SandboxExecutor()._wrap_code("print('hi')", d)

    with tempfile.TemporaryDirectory() as d2:
        f = Path(d2) / "_wrapped.py"
        f.write_text(wrapped, encoding="utf-8")
        ok = compileall.compile_file(str(f), quiet=2, force=True)
    assert ok, "生成的沙箱包装代码无法编译"


# 注意：不要在 pytest 进程内 exec 前置码来「验证屏蔽生效」。前置码会往**真实**
# sys.meta_path / sys.path 里插 finder 并 chdir，直接把宿主进程毒掉——实测这会让
# 同一会话里后续的 `import app.main` 全部报「沙箱禁止导入后端源码包」。
# 机制由上面两个静态单测 + 下面真实子进程的不变量测试共同锁住，不需要内联 exec。


# ── 后端选择与回退 ─────────────────────────────────────


def test_docker_used_only_when_daemon_and_image_ready():
    """docker 模式要求 daemon 连通 **且** 镜像存在；缺任一都应回退 subprocess。"""
    if docker_daemon_up() and not docker_image_ready():
        # 这正是 2026-10 CI 的现场：runner 上 docker 活着但没 build 镜像
        ex = SandboxExecutor()
        assert ex.backend == "docker", "配置项应为 docker"
        r = ex.run("print('fallback-ok')")
        assert r.get("success"), f"镜像缺失时应回退 subprocess 并跑通: {r}"
        assert "fallback-ok" in (r.get("stdout") or ""), r


def test_sandbox_status_endpoint_reports_image_readiness():
    """/api/sandbox/status 必须把镜像缺失也反映出来，不能只报 docker_available。"""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.get("/api/sandbox/status")
        assert r.status_code == 200
        body = r.json()
        assert "docker_image_ready" in body, "状态接口没暴露镜像就绪度"
        assert body["docker_image_ready"] == (body["docker_available"] and docker_image_ready())
        # 口径一致性：报 docker 就必须真的两个条件都满足
        if body["backend"] == "docker":
            assert body["docker_available"] and body["docker_image_ready"]


def test_image_constant_matches_dockerfile():
    """镜像名与 Dockerfile.sandbox 的 build tag 必须一致（CI 要按它 build）。"""
    assert SANDBOX_IMAGE == "mathmodel-sandbox"


if __name__ == "__main__":
    for _fn in [
        test_import_backend_config_blocked,
        test_import_backend_submodules_blocked,
        test_backend_source_not_reachable_after_sys_path_reinjection,
        test_project_root_not_on_sys_path,
        test_network_still_blocked,
        test_normal_scientific_stack_still_works,
        test_wrap_code_contains_source_isolation_prelude,
        test_wrap_code_output_is_valid_python,
        test_docker_used_only_when_daemon_and_image_ready,
        test_sandbox_status_endpoint_reports_image_readiness,
        test_image_constant_matches_dockerfile,
    ]:
        _fn()
        print(f"PASSED {_fn.__name__}")
    print(f"(effective backend: {_BACKEND})")
    print("ALL TESTS PASSED")
