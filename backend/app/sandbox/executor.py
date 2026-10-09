"""代码沙箱 — subprocess 或 Docker 安全执行 Python 代码。

安全措施:
  - subprocess 模式: 内存/CPU/文件大小限制 (Unix resource.setrlimit) + socket monkey-patch
  - Docker 模式: --network=none --memory=512m 硬隔离（跨平台，推荐）
  - 环境变量清洗 (不泄露父进程 API key)
  - 执行超时
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)


def _smart_truncate(text: str, limit: int = 2000) -> str:
    """截断保头+保尾。

    stderr 的异常类型/行号在 traceback 末尾、stdout 的求解结果在打印末尾——
    单纯保头会把最关键的信息切掉，LLM 自修复循环拿到的是文件头不是错误本体
    （审查 P1）。头部保留少量上下文，尾部完整保留。
    """
    if len(text) <= limit:
        return text
    head_len = min(400, limit // 5)
    tail_len = limit - head_len - 30
    return f"{text[:head_len]}\n...(中间省略 {len(text) - head_len - tail_len} 字符)...\n{text[-tail_len:]}"


def _dedupe_image_paths(paths: list[Path]) -> list[Path]:
    """按图片内容 MD5 去重。

    用户代码手动 plt.savefig('xxx.png') 与沙箱自动保存（figure_N.png）常是
    同一张图的两次落盘——去重后只留一张（优先保留用户手动命名的文件）。
    """
    if len(paths) <= 1:
        return paths
    seen: dict[str, Path] = {}
    # 手动命名文件排在前面登记，自动命名的重复副本被丢弃
    ordered = sorted(paths, key=lambda p: p.name.startswith("figure_"))
    for p in ordered:
        try:
            digest = hashlib.md5(p.read_bytes()).hexdigest()
        except Exception:
            digest = f"path:{p}"
        seen.setdefault(digest, p)
    return [seen[k] for k in seen]

# ── Docker 沙箱镜像名 ──────────────────────────────────────────────

SANDBOX_IMAGE = "mathmodel-sandbox"

# Docker 守护进程探测缓存（避免每次执行都探测；失败后 60s 内不重试）
_daemon_probe = {"ok": None, "ts": 0.0}


def docker_daemon_up() -> bool:
    """探测 Docker 守护进程是否可用（结果缓存 60 秒）。

    docker CLI 已安装但 Docker Desktop 未启动时 `docker run` 会直接失败，
    因此「可用」= 二进制存在 **且** daemon 可连通。
    """
    import time as _time

    now = _time.monotonic()
    if _daemon_probe["ok"] is not None and (now - _daemon_probe["ts"]) < 60:
        return _daemon_probe["ok"]

    ok = False
    try:
        probe = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        ok = probe.returncode == 0 and bool(probe.stdout.strip())
    except Exception:
        ok = False

    _daemon_probe["ok"] = ok
    _daemon_probe["ts"] = now
    if not ok:
        logger.warning(
            "docker 守护进程不可用（未安装或 Docker Desktop 未启动），"
            "沙箱回退 subprocess 模式（仅限可信输入）"
        )
    return ok


def _make_preexec_fn(max_memory_mb: int, timeout: int):
    """创建 Unix preexec_fn 设置资源限制。Windows 下返回 None。"""
    try:
        import resource
    except ImportError:
        return None

    def _set_limits():
        # 虚拟地址空间给足（numpy/OpenBLAS 会映射大量 VA，RLIMIT_AS 太紧会 import 即崩）；
        # 真实内存上限由 _run_subprocess 的 psutil 进程树 RSS 监控守护
        va_bytes = max_memory_mb * 4 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (va_bytes, va_bytes))
        # RLIMIT_CPU 按 CPU 时间计：BLAS 双线程下约 30s 墙钟就能烧掉 60s CPU
        # 预算，进程被 SIGXCPU 杀掉且 stderr 可能为空——上游误判成功（审查 A）。
        # 墙钟主限由 communicate(timeout=...) 把关，这里只做慷慨兜底。
        cpu_budget = timeout * 2 + 30
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_budget, cpu_budget))
        file_limit = 50 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
        # 必须允许线程：OpenBLAS/matplotlib 要起工作线程；硬进程隔离靠 docker 模式
        resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))

    return _set_limits


def _find_tesseract() -> str | None:
    """定位本机 tesseract 二进制（subprocess 沙箱 OCR 用）。"""
    import shutil as _shutil

    found = _shutil.which("tesseract")
    if found:
        return found
    for cand in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if os.path.exists(cand):
            return cand
    return None


def _find_tessdata() -> str | None:
    """定位 OCR 语言包目录（项目内 data/tessdata，含 chi_sim/eng/osd）。"""
    try:
        settings = get_settings()
        cand = settings.project_root / "data" / "tessdata"
        if cand.exists() and any(cand.glob("*.traineddata")):
            return str(cand)
    except Exception:
        pass
    return None


def _clean_env() -> dict:
    """构建清洗后的子进程环境变量，仅保留 Python 运行必需项。

    注意：刻意排除 PYTHONPATH —— 项目是 editable 安装，若继承 PYTHONPATH，
    沙箱代码可 `import app.config` 直接读取后端密钥（API Key/JWT secret）。
    """
    safe_keys = {
        "PATH",
        "PYTHONIOENCODING",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "SYSTEMROOT",
        "COMSPEC",
        "APPDATA",
        "LOCALAPPDATA",
    }
    env = {k: v for k, v in os.environ.items() if k.upper() in safe_keys}
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("HTTP_PROXY", None)
    env.pop("HTTPS_PROXY", None)
    env.pop("http_proxy", None)
    env.pop("https_proxy", None)
    # 限制 BLAS 线程数：降低线程开销与内存峰值（numpy/scipy/matplotlib 共享）
    env["OPENBLAS_NUM_THREADS"] = "2"
    env["OMP_NUM_THREADS"] = "2"
    env["MKL_NUM_THREADS"] = "2"

    # OCR 能力注入（subprocess 模式）：tesseract 二进制加入 PATH，
    # 语言包目录经 TESSDATA_PREFIX 指向（pytesseract 默认只认这两处）。
    _tesseract = _find_tesseract()
    if _tesseract:
        env["PATH"] = str(Path(_tesseract).parent) + os.pathsep + env.get("PATH", "")
    _tessdata = _find_tessdata()
    if _tessdata:
        env["TESSDATA_PREFIX"] = _tessdata

    return env


class SandboxExecutor:
    """在受限子进程或 Docker 容器中执行 Python 代码。

    模式选择:
      - SANDBOX_BACKEND=subprocess (默认): 用 subprocess 在本机执行
      - SANDBOX_BACKEND=docker: 用 docker run --rm 隔离执行（需先构建镜像）
    """

    def __init__(self, timeout: int | None = None):
        settings = get_settings()
        self.timeout = timeout or settings.sandbox_timeout
        self.max_memory_mb = settings.sandbox_max_memory_mb
        self.backend = settings.sandbox_backend
        self.output_dir = Path(tempfile.gettempdir()) / "mathmodel_outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── public API ────────────────────────────────────────────────

    def run(
        self,
        code: str,
        extra_files: list[str] | None = None,
        cancel_event=None,
    ) -> dict:
        """执行代码，返回 stdout、stderr、图片路径列表。

        extra_files: 可选，需要复制到沙箱工作目录的文件绝对路径列表。
        cancel_event: 可选 threading.Event；置位时立即中断执行（事件级取消）。
        """
        run_id = str(uuid.uuid4())[:8]
        output_subdir = self.output_dir / run_id
        output_subdir.mkdir(parents=True, exist_ok=True)

        # 复制额外文件到沙箱工作目录
        if extra_files:
            import shutil as _shutil

            for fpath in extra_files:
                try:
                    _shutil.copy2(fpath, str(output_subdir / Path(fpath).name))
                except Exception as e:
                    logger.warning("复制文件到沙箱失败 %s: %s", fpath, e)

        if self.backend == "docker":
            # 优先 docker（硬隔离）；二进制缺失或 daemon 未启动 → 自动回退 subprocess
            if docker_daemon_up():
                result = self._run_docker(code, output_subdir, run_id, cancel_event)
            else:
                result = self._run_subprocess(code, output_subdir, run_id, cancel_event)
        else:
            result = self._run_subprocess(code, output_subdir, run_id, cancel_event)

        # 图片/结果文件落盘持久副本：系统临时目录被清理后引用仍有效
        self._persist_chat_outputs(result, run_id)
        return result

    def _persist_chat_outputs(self, result: dict, run_id: str) -> None:
        """把执行产物复制到 data/chat_images/{run_id}（best-effort）。

        聊天模式的图片只留在 temp 目录时，Windows 重启/磁盘清理会全部 404，
        前端出现"图和动画引用出现问题"；持久副本 + get_image 路由 fallback 兜底。
        """
        try:
            import shutil as _shutil

            settings = get_settings()
            dest = settings.project_root / "data" / "chat_images" / run_id
            dest.mkdir(parents=True, exist_ok=True)
            for key in ("images", "xlsx_files", "csv_files", "html_files"):
                for fpath in result.get(key, []):
                    try:
                        _shutil.copy2(fpath, str(dest / Path(fpath).name))
                    except Exception:
                        pass
        except Exception:
            pass  # 持久化失败不影响执行结果
        finally:
            self._cleanup_stale_outputs()

    def _cleanup_stale_outputs(self) -> None:
        """清理陈旧的沙箱输出目录（temp 与 data/chat_images 防磁盘缓慢增长）。

        保留最近 KEEP=50 个目录；只删除修改时间超过 24h 的旧目录，
        避免误删仍在并发执行中的沙箱工作目录。
        """
        import shutil as _shutil
        import time as _time

        keep = 50
        cutoff = _time.time() - 86400  # 24 小时
        roots: list[Path] = [self.output_dir]
        try:
            roots.append(get_settings().project_root / "data" / "chat_images")
        except Exception:
            pass

        for root in roots:
            try:
                if not root.exists():
                    continue
                dirs = sorted(
                    (p for p in root.iterdir() if p.is_dir()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                for stale in dirs[keep:]:
                    try:
                        if stale.stat().st_mtime < cutoff:
                            _shutil.rmtree(stale, ignore_errors=True)
                            logger.info("已清理陈旧沙箱输出目录: %s", stale)
                    except Exception:
                        pass
            except Exception:
                pass  # 清理失败不影响执行

    # ── subprocess 模式 ──────────────────────────────────────────

    def _run_subprocess(
        self, code: str, output_subdir: Path, run_id: str, cancel_event=None
    ) -> dict:
        """在本机子进程中执行 + psutil 进程树内存监控（Windows 无 rlimit 的补偿）。

        监控线程每 0.3s 汇总父进程+全部子进程 RSS，超 max_memory_mb 即杀整树，
        防止大 DataFrame 操作吃光内存导致后端主进程被系统 OOM 杀掉；
        同时检查任务取消事件（置位 → 立即中断，事件级取消）。
        """
        wrapped_code = self._wrap_code(code, str(output_subdir))

        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", wrapped_code],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(output_subdir),
                encoding="utf-8",
                errors="replace",
                env=_clean_env(),
                preexec_fn=_make_preexec_fn(self.max_memory_mb, self.timeout),
            )

            oom_killed = {"hit": False}
            cancelled = {"hit": False}

            def _kill_tree():
                import psutil

                try:
                    parent = psutil.Process(proc.pid)
                    for child in parent.children(recursive=True):
                        try:
                            child.kill()
                        except Exception:
                            pass
                    try:
                        parent.kill()
                    except Exception:
                        pass
                except psutil.NoSuchProcess:
                    try:
                        proc.kill()
                    except Exception:
                        pass

            def _monitor():
                try:
                    import time as _time

                    import psutil

                    limit = self.max_memory_mb * 1024 * 1024
                    parent = psutil.Process(proc.pid)
                    while proc.poll() is None:
                        # 取消检查优先：任务被取消 → 立即中断整棵进程树
                        if cancel_event is not None and cancel_event.is_set():
                            cancelled["hit"] = True
                            _kill_tree()
                            break
                        try:
                            rss = parent.memory_info().rss
                            for child in parent.children(recursive=True):
                                rss += child.memory_info().rss
                        except psutil.NoSuchProcess:
                            break
                        if rss > limit:
                            oom_killed["hit"] = True
                            _kill_tree()
                            break
                        _time.sleep(0.3)
                except Exception:
                    pass  # 监控失败不影响执行

            import threading

            monitor = threading.Thread(target=_monitor, daemon=True)
            monitor.start()

            try:
                stdout, stderr = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                _kill_tree()
                # 回传超时前的部分输出（审查 A3）：旧实现丢弃 communicate()
                # 的返回值，LLM 自修复循环拿不到任何中间结果，只能盲猜。
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except Exception:
                    stdout, stderr = "", ""
                partial = _smart_truncate(stdout or "", 3000)
                return {
                    "success": False,
                    "stdout": partial,
                    "stderr": (
                        f"执行超时 ({self.timeout}秒)，进程已被终止。"
                        + (
                            "以下是超时前已产生的部分输出，请据此拆分任务规模/迭代次数后重试：\n"
                            + _smart_truncate(stderr or "", 1000)
                            if stderr
                            else "请把计算拆小（降低规模/迭代上限/采样）后重试，原样重跑只会再次超时。"
                        )
                    ),
                    "returncode": -1,
                    "images": [],
                    "xlsx_files": [],
                    "csv_files": [],
                    "html_files": [],
                    "run_id": run_id,
                }

            if cancelled["hit"]:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "执行已被取消",
                    "returncode": -1,
                    "images": [],
                    "xlsx_files": [],
                    "csv_files": [],
                    "html_files": [],
                    "run_id": run_id,
                }

            if oom_killed["hit"]:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"内存超限（>{self.max_memory_mb}MB），已终止执行。请减小数据规模或改用 docker 沙箱。",
                    "returncode": -1,
                    "images": [],
                    "xlsx_files": [],
                    "csv_files": [],
                    "html_files": [],
                    "run_id": run_id,
                }

            images = _dedupe_image_paths(
                sorted(
                    list(output_subdir.glob("*.png"))
                    + list(output_subdir.glob("*.jpg"))
                    + list(output_subdir.glob("*.jpeg"))
                    + list(output_subdir.glob("*.gif"))
                    + list(output_subdir.glob("*.webp"))
                )
            )
            xlsx_files = sorted(output_subdir.glob("*.xlsx"))
            csv_files = sorted(output_subdir.glob("*.csv"))
            html_files = sorted(output_subdir.glob("*.html"))
            return {
                "success": proc.returncode == 0,
                "stdout": _smart_truncate(stdout, 5000),
                "stderr": _smart_truncate(stderr, 2000),
                "returncode": proc.returncode,
                "images": [str(img) for img in images],
                "xlsx_files": [str(f) for f in xlsx_files],
                "csv_files": [str(f) for f in csv_files],
                "html_files": [str(f) for f in html_files],
                "run_id": run_id,
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "images": [],
                "xlsx_files": [],
                "csv_files": [],
                "html_files": [],
                "run_id": run_id,
            }

    # ── Docker 模式 ──────────────────────────────────────────────

    def _run_docker(self, code: str, output_subdir: Path, run_id: str, cancel_event=None) -> dict:
        """在 Docker 容器中隔离执行。

        安全: --network=none 阻断网络, --memory 硬限制内存,
              --rm 执行完自动销毁, 不残留文件系统状态。
        支持事件级取消：取消置位时 kill 容器（docker run 前台进程 + docker kill 兜底）。
        """
        # 将代码写入临时文件，挂载进容器
        code_file = output_subdir / "_code.py"
        code_file.write_text(code, encoding="utf-8")

        # 容器内输出目录
        container_output = "/output"
        container_name = f"mma-sandbox-{run_id}"

        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network=none",
            f"--memory={self.max_memory_mb}m",
            f"--memory-swap={self.max_memory_mb}m",  # 禁用 swap
            "--cap-drop=ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "-e",
            "HOME=/tmp",
            "-e",
            "MPLCONFIGDIR=/tmp/matplotlib",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-e",
            "OPENBLAS_NUM_THREADS=2",
            "-e",
            "OMP_NUM_THREADS=2",
            "-e",
            "MKL_NUM_THREADS=2",
            "-v",
            f"{output_subdir}:{container_output}:rw",
            SANDBOX_IMAGE,
            f"{container_output}/_code.py",
            container_output,
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            def _kill_container():
                """杀 docker run 前台进程 + docker kill 容器兜底（--rm 会自动清理）。"""
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    subprocess.run(
                        ["docker", "kill", container_name],
                        capture_output=True,
                        timeout=5,
                    )
                except Exception:
                    pass

            # 轮询等待：超时 / 取消 → 中断容器。Docker Desktop 冷启动/镜像层
            # 加载常超 10s，宽限给足（审查 A2），否则「启动慢」也被记成代码超时
            import time as _time

            deadline = _time.monotonic() + self.timeout + 25
            cancelled = False
            while proc.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    _kill_container()
                    break
                if _time.monotonic() > deadline:
                    _kill_container()
                    break
                _time.sleep(0.5)
            stdout, stderr = proc.communicate()

            images = _dedupe_image_paths(
                sorted(
                    p
                    for p in (
                        list(output_subdir.glob("*.png"))
                        + list(output_subdir.glob("*.jpg"))
                        + list(output_subdir.glob("*.jpeg"))
                        + list(output_subdir.glob("*.gif"))
                        + list(output_subdir.glob("*.webp"))
                    )
                    if p.name != "_code.py"
                )
            )
            xlsx_files = sorted(p for p in output_subdir.glob("*.xlsx") if p.name != "_code.py")
            csv_files = sorted(p for p in output_subdir.glob("*.csv") if p.name != "_code.py")
            html_files = sorted(p for p in output_subdir.glob("*.html") if p.name != "_code.py")

            if cancelled:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "执行已被取消",
                    "returncode": -1,
                    "images": [],
                    "xlsx_files": [],
                    "csv_files": [],
                    "html_files": [],
                    "run_id": run_id,
                }
            if proc.returncode != 0 and not stderr and not stdout:
                # 轮询超时杀掉的进程 returncode 为 -9，无输出 → 判定超时
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        f"执行超时 ({self.timeout}秒)，容器已被终止。"
                        "请把计算拆小（降低规模/迭代上限/采样）后重试，原样重跑只会再次超时。"
                    ),
                    "returncode": -1,
                    "images": [],
                    "xlsx_files": [],
                    "csv_files": [],
                    "html_files": [],
                    "run_id": run_id,
                }

            if proc.returncode != 0 and "执行超时" in (stderr or ""):
                # wrapper 侧报告的代码超时：透传部分 stdout 供自修复参考（审查 A3）
                return {
                    "success": False,
                    "stdout": _smart_truncate(stdout or "", 3000),
                    "stderr": _smart_truncate(stderr, 2000),
                    "returncode": proc.returncode,
                    "images": [str(img) for img in images],
                    "xlsx_files": [str(f) for f in xlsx_files],
                    "csv_files": [str(f) for f in csv_files],
                    "html_files": [str(f) for f in html_files],
                    "run_id": run_id,
                }

            return {
                "success": proc.returncode == 0,
                "stdout": _smart_truncate(stdout, 5000),
                "stderr": _smart_truncate(stderr, 2000),
                "returncode": proc.returncode,
                "images": [str(img) for img in images],
                "xlsx_files": [str(f) for f in xlsx_files],
                "csv_files": [str(f) for f in csv_files],
                "html_files": [str(f) for f in html_files],
                "run_id": run_id,
            }
        except FileNotFoundError:
            return {
                "success": False,
                "stdout": "",
                "stderr": (
                    "Docker 未安装或未在 PATH 中。请安装 Docker Desktop，"
                    "然后执行: docker build -t mathmodel-sandbox -f Dockerfile.sandbox ."
                ),
                "returncode": -1,
                "images": [],
                "xlsx_files": [],
                "csv_files": [],
                "html_files": [],
                "run_id": run_id,
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "images": [],
                "xlsx_files": [],
                "csv_files": [],
                "html_files": [],
                "run_id": run_id,
            }

    def _wrap_code(self, code: str, output_dir: str) -> str:
        """包装用户代码：阻断网络 + 按需导入 + 自动捕获 matplotlib 输出。

        不再预导入 numpy/scipy/pandas —— LLM 生成的代码自带 import，预导入浪费
        200-500MB 内存每个沙箱进程。matplotlib 也改为按需配置（meta_path hook：
        用户代码第一次 import matplotlib 时才设 Agg + 中文字体 + savefig 跟踪），
        纯计算代码不再为画图能力白付约 1s 启动开销。
        """
        return f"""
# ── 网络阻断：禁止任何 socket 连接（connect + connect_ex 双拦）──
import socket as _socket
_original_connect = _socket.socket.connect
_original_connect_ex = _socket.socket.connect_ex
def _blocked_connect(self, *args, **kwargs):
    raise OSError("网络访问已被沙箱禁止")
def _blocked_connect_ex(self, *args, **kwargs):
    raise OSError("网络访问已被沙箱禁止")
_socket.socket.connect = _blocked_connect
_socket.socket.connect_ex = _blocked_connect_ex
del _socket, _original_connect, _original_connect_ex

import sys as _sys
import os as _os

# ── matplotlib 按需配置（deferred）──
# 旧实现预热 import matplotlib + 扫系统字体，每次沙箱执行固定多付约 1s，
# 纯计算代码（不画图）也照付；更糟的是超时预算被启动开销吃掉——timeout=2
# 的回归测试会在用户代码 print 之前就把进程杀掉，partial stdout 丢失
# （test_subprocess_timeout_returns_partial_stdout 的 flaky 根因）。
# 改为：用户代码第一次 import matplotlib 时才配 Agg + 中文字体 + savefig 跟踪。
from importlib.abc import MetaPathFinder as _MetaPathFinder

_saved_figs = set()
_mpl_ready = False


def _configure_matplotlib():
    global _mpl_ready
    if _mpl_ready:
        return
    _mpl_ready = True  # 先置位再 import，防 find_spec 重入
    try:
        import matplotlib as _mpl

        _mpl.use("Agg")  # 必须在任何 pyplot import 之前
        try:
            import matplotlib.font_manager as _fm

            _candidates = [
                "Noto Sans CJK SC", "Microsoft YaHei", "SimHei",
                "PingFang SC", "WenQuanYi Micro Hei", "Source Han Sans SC",
            ]
            _available = {{_f.name for _f in _fm.fontManager.ttflist}}
            for _c in _candidates:
                if _c in _available:
                    _mpl.rcParams["font.sans-serif"] = [_c] + list(
                        _mpl.rcParams["font.sans-serif"]
                    )
                    break
            _mpl.rcParams["axes.unicode_minus"] = False
            del _fm
        except Exception:
            pass
        # savefig 跟踪：自动保存时跳过用户已手动保存的图（避免同图落盘两份）
        import matplotlib.figure as _mfig

        _orig_savefig = _mfig.Figure.savefig

        def _tracked_savefig(self, *args, **kwargs):
            _saved_figs.add(id(self))
            return _orig_savefig(self, *args, **kwargs)

        _mfig.Figure.savefig = _tracked_savefig
    except Exception:
        pass


class _DeferMatplotlib(_MetaPathFinder):
    # 只拦 matplotlib.pyplot：import 系统保证触发子模块查找时父包已完整导入，
    # 此时配置 Agg/字体/savefig 安全。若在 find_spec("matplotlib") 里 import
    # matplotlib，拿到的是半初始化模块（use 未定义），pyplot 后续会炸
    # AttributeError: module 'matplotlib' has no attribute 'artist'。
    # 返回 None 让常规 finder 继续正常导入。
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "matplotlib.pyplot":
            _configure_matplotlib()
        return None


_sys.meta_path.insert(0, _DeferMatplotlib())

_os.chdir({json.dumps(output_dir)})

# ── 用户代码（LLM 自行 import 所需库）──
{code}

# ── 自动保存 matplotlib 图表（仅当用户代码用到了 pyplot；跳过已手动保存的）──
if "matplotlib.pyplot" in _sys.modules:
    import matplotlib.pyplot as _plt
    for i in _plt.get_fignums():
        fig = _plt.figure(i)
        if id(fig) in _saved_figs:
            continue
        fig.savefig(_os.path.join({json.dumps(output_dir)}, f"figure_{{i}}.png"),
                    dpi=150, bbox_inches="tight")
    _plt.close("all")
"""
