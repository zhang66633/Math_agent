"""沙箱后端源码隔离回归测试（审计 2026-10 P0）。

背景：项目 editable 安装生成的 `math_model_agent.pth` 内容就是 `<repo>/backend`，
由 `site` 模块在解释器启动时无条件写进 `sys.path`——只从 env 删 PYTHONPATH 挡不住。
修复前沙箱代码可 `import app.config` 直读 `.env` 的 JWT_SECRET / API Key
（已实证复现）；修复后在 `_wrap_code` 生成的前置码里剔除仓库根 + meta_path 屏蔽。

运行: 在 backend/ 目录下 `python -m pytest tests/test_sandbox_source_isolation.py -q`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sandbox.executor import SandboxExecutor  # noqa: E402

# 这些用例都跑在真实子进程里（与线上同一条 _run_subprocess 路径），
# 因此能覆盖 .pth → sys.path 这条只在子进程启动时发生的链路。
_EXEC = SandboxExecutor(timeout=90)


def _run(code: str) -> dict:
    return _EXEC.run(code)


def test_import_backend_config_blocked():
    """import app.config 必须失败——这是泄露 .env 密钥的直接通道。"""
    r = _run("import app.config\nprint('LEAKED')")
    out = r.get("stdout") or ""
    err = r.get("stderr") or ""
    assert "LEAKED" not in out, f"沙箱仍能导入后端源码: {out}"
    assert "沙箱禁止导入后端源码包" in err or "ModuleNotFoundError" in err, (
        f"未拿到预期的导入阻断信息: {err[:300]}"
    )


def test_import_backend_submodules_blocked():
    """app 的子包同样要挡住（app.core.nodes / app.config 等）。"""
    for mod in ("app.core.nodes", "app.api.apikeys", "app.services.session"):
        r = _run(f"import {mod}\nprint('LEAKED')")
        assert "LEAKED" not in (r.get("stdout") or ""), f"{mod} 竟可导入"
        assert "沙箱禁止导入后端源码包" in (r.get("stderr") or ""), (
            f"{mod} 未拿到预期的阻断信息"
        )


def test_project_root_stripped_from_sys_path():
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


def test_sys_path_reinjection_still_blocked():
    """即便用户代码把路径加回 sys.path，meta_path 屏蔽依然生效。"""
    code = (
        "import sys, os\n"
        f"sys.path.append({str(Path(__file__).resolve().parent.parent)!r})\n"
        "import app.config\n"
        "print('LEAKED')\n"
    )
    r = _run(code)
    assert "LEAKED" not in (r.get("stdout") or ""), "sys.path 重新注入后仍可导入后端源码"
    assert "沙箱禁止导入后端源码包" in (r.get("stderr") or "")


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


def test_network_still_blocked():
    """回归护栏：socket 阻断不能因本次改动失效。"""
    r = _run(
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 443), timeout=3)\n"
        "    print('NET_OPEN')\n"
        "except Exception as e:\n"
        "    print('NET_CLOSED', type(e).__name__)\n"
    )
    assert "NET_CLOSED" in (r.get("stdout") or ""), r.get("stdout")


if __name__ == "__main__":
    for _fn in (
        test_import_backend_config_blocked,
        test_import_backend_submodules_blocked,
        test_project_root_stripped_from_sys_path,
        test_sys_path_reinjection_still_blocked,
        test_normal_scientific_stack_still_works,
        test_network_still_blocked,
    ):
        _fn()
        print(f"PASSED {_fn.__name__}")
    print("ALL TESTS PASSED")
