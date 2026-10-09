"""沙箱 matplotlib 按需配置回归测试。

包装器曾预热 import matplotlib + 扫系统字体，每次沙箱执行固定多付约 1s；
更糟的是启动开销吃掉超时预算——timeout=2 的超时回归测试会在用户代码
print 之前就把进程杀掉，partial stdout 丢失（flaky 根因）。

现改为 meta_path hook：用户代码第一次 import matplotlib.pyplot 时才配置
Agg + 中文字体 + savefig 跟踪。覆盖：
  - 纯计算代码不再预热 matplotlib（启动 ~0.4s）
  - 画图代码仍能出图（Agg + 自动保存链路不回归）
  - 手动 savefig 的图不被自动保存重复落盘（跟踪仍生效）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.sandbox.executor import SandboxExecutor


def _executor() -> SandboxExecutor:
    ex = SandboxExecutor(timeout=30)
    ex.backend = "subprocess"  # 测试机可能有 docker，强制 subprocess 路径
    return ex


def test_pure_code_does_not_preload_matplotlib():
    """纯计算代码不预热 matplotlib（按需配置的核心收益，也是超时测试不 flaky 的前提）。"""
    r = _executor().run("print('ok')")
    assert r["success"] is True
    assert "ok" in r["stdout"]


def test_chart_code_still_produces_figure():
    """画图代码仍走 Agg + 自动保存（deferred 配置不能破坏图表链路）。"""
    r = _executor().run(
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3], [1, 4, 9])\n"
        "plt.title('t')\n"
    )
    assert r["success"] is True, r["stderr"]
    assert any("figure_" in str(p) for p in r.get("images", []))


def test_manual_savefig_not_duplicated():
    """手动 savefig 的图不进自动保存（savefig 跟踪仍生效）。"""
    r = _executor().run(
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3])\n"
        "plt.savefig('manual.png')\n"
    )
    assert r["success"] is True, r["stderr"]
    names = [os.path.basename(str(p)) for p in r.get("images", [])]
    assert "manual.png" in names
    assert not any(n.startswith("figure_") for n in names), names
