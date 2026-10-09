"""MathModelAgent 统一入口 — install / start / stop 三个子命令（跨平台）。

用法::

    python start.py                 # 等同于 start
    python start.py start           # 启动前后端
    python start.py install         # 一键安装（venv + 依赖 + .env + 前端依赖）
    python start.py install --docker  # 额外构建沙箱镜像并启用硬隔离
    python start.py stop            # 停止前后端（按端口找进程，跨平台）
    python start.py --help

为什么保留 start.bat：cmd.exe 逐字节读批处理，多字节中文可能被它的读缓冲区
从中间劈开、碎片被当成命令执行（曾随机报 "'xxx' is not recognized"）。所以
start.bat 保持纯 ASCII 只做转发，全部逻辑放在本文件，编码由 Python 掌控。

历史：install.bat / install.py / install.sh / stop.bat / start.py 五份脚本
三套操作系统各写一遍，逻辑已漂移（start.py 端口硬编码、stop.bat 容器名不对、
install.py 与 install.sh 的 .env 替换项不一致）。2026-09 收敛为本文件。
"""

import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_PORT = "8002"
FRONTEND_PORT = "5174"
IS_WINDOWS = sys.platform == "win32"


def venv_python() -> str:
    """项目 .venv 的解释器路径（Windows 与 POSIX 布局不同）。"""
    if IS_WINDOWS:
        cand = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        cand = ROOT / ".venv" / "bin" / "python"
    return str(cand) if cand.exists() else sys.executable


def log(msg: str) -> None:
    print(msg, flush=True)


def press_any_key(msg: str) -> None:
    """等待按键;stdin 被重定向(如 start.bat > log)时避免 EOFError 崩溃"""
    try:
        input(msg)
    except EOFError:
        pass


def run(args, error_msg: str, cwd: Path | None = None, fatal: bool = True):
    """运行外部命令，失败时打印 error_msg；fatal=True 时退出 1。"""
    log("  > " + " ".join(str(a) for a in args))
    try:
        result = subprocess.run(args, cwd=str(cwd) if cwd else str(ROOT), check=False)
    except OSError as exc:
        log(f"[错误] {error_msg}：{exc}")
        if fatal:
            sys.exit(1)
        return None
    if result.returncode != 0:
        log(f"[错误] {error_msg}（退出码 {result.returncode}）")
        if fatal:
            sys.exit(1)
    return result


# ── install ────────────────────────────────────────────────────────────


def cmd_install(use_docker: bool) -> None:
    log("=" * 46)
    log("  Math Model Agent — 一键安装")
    log("=" * 46)

    # ── 1. 环境检查 ──
    if sys.version_info < (3, 11):
        log(f"[错误] Python 版本过低,需要 3.11+,当前为 {sys.version.split()[0]}")
        log("        https://www.python.org/downloads/")
        sys.exit(1)
    log(f"[1/5] Python 版本: {sys.version.split()[0]}")

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        log("[错误] 未找到 pnpm。请先安装:")
        log("        npm i -g pnpm")
        log("     或: corepack enable")
        sys.exit(1)
    log("[1/5] pnpm 已就绪")

    # ── 2. 后端: 虚拟环境 ──
    venv_dir = ROOT / ".venv"
    if (venv_dir / "Scripts" / "python.exe").exists() or (
        venv_dir / "bin" / "python"
    ).exists():
        log("[2/5] 虚拟环境 .venv 已存在, 跳过")
    else:
        log("[2/5] 创建虚拟环境 .venv ...")
        run([sys.executable, "-m", "venv", str(venv_dir)], "创建虚拟环境失败")

    # ── 3. 后端依赖 ──
    py = venv_python()
    log("[3/5] 安装后端依赖(首次约 3-8 分钟,取决于网络)...")
    # 升级 pip 失败不致命,静默忽略
    subprocess.run(
        [py, "-m", "pip", "install", "--upgrade", "pip"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    run([py, "-m", "pip", "install", "-e", "backend"], "后端依赖安装失败,请检查网络后重试")

    # ── 4. 生成 .env ──
    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        log("[4/5] backend/.env 已存在, 跳过")
    else:
        log("[4/5] 生成 backend/.env 并注入随机 JWT_SECRET")
        example = BACKEND_DIR / ".env.example"
        if not example.exists():
            log("[错误] 未找到 backend/.env.example,仓库文件不完整,请重新下载解压")
            sys.exit(1)
        text = example.read_text(encoding="utf-8")
        text = text.replace(
            "JWT_SECRET=change-me-to-a-random-string",
            "JWT_SECRET=" + secrets.token_hex(32),
        )
        # 与 install.sh 对齐：端口归一到 8002、沙箱默认 subprocess
        text = text.replace("PORT=8000", "PORT=8002")
        text = text.replace("SANDBOX_BACKEND=docker", "SANDBOX_BACKEND=subprocess")
        env_file.write_text(text, encoding="utf-8")

    # ── 5. 前端依赖 ──
    log("[5/5] 安装前端依赖 pnpm install(首次约 2-5 分钟)...")
    if not (FRONTEND_DIR / "package.json").exists():
        log("[错误] 未找到 frontend/package.json,仓库文件不完整,请重新下载解压")
        sys.exit(1)
    # 用 cwd 而不是 --dir:进程级锁定工作目录,与调用方当前目录完全无关
    run([pnpm, "install"], "前端依赖安装失败", cwd=FRONTEND_DIR)

    # ── 可选: Docker 沙箱镜像 ──
    if use_docker:
        docker = shutil.which("docker")
        if docker is None:
            log("[警告] 未检测到 docker,继续使用 subprocess 模式(功能不受影响)")
        else:
            log("[可选] 构建沙箱镜像 mathmodel-sandbox ...")
            result = run(
                [docker, "build", "-t", "mathmodel-sandbox",
                 "-f", "backend/Dockerfile.sandbox", "backend"],
                "沙箱镜像构建失败,继续使用 subprocess 模式(功能不受影响)",
                fatal=False,
            )
            if result is not None and result.returncode == 0:
                if env_file.exists():
                    text = env_file.read_text(encoding="utf-8")
                    text = text.replace(
                        "SANDBOX_BACKEND=subprocess", "SANDBOX_BACKEND=docker"
                    )
                    env_file.write_text(text, encoding="utf-8")
                log("[可选] 已启用 docker 硬隔离沙箱")

    log("")
    log("=" * 46)
    log("  安装完成!")
    log("")
    log("  启动:  python start.py   (或 start.bat)")
    log("  前端:  http://localhost:5174")
    log("  后端:  http://127.0.0.1:8002/docs")
    log("")
    log("  配置 API Key: 打开首页,在「API Key」输入框粘贴你的")
    log("  DeepSeek/OpenAI 兼容 Key 即可(仅保存在本机 backend\\data)。")
    log("  也可以编辑 backend\\.env 填 OPENAI_API_KEY。")
    log("=" * 46)


# ── start ──────────────────────────────────────────────────────────────


def check_env() -> bool:
    """检查 .env 是否已配置"""
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        log("[ERROR] backend/.env 不存在!")
        log("  请先运行: python start.py install")
        return False
    return True


def check_port(port: str) -> bool:
    """检查端口是否已被占用（已监听）"""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", int(port)))
        s.close()
        return True
    except Exception:
        # 连接失败即视为未监听；探测失败绝不能让启动器崩掉
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def start_process(name: str, cwd: Path, cmd: str) -> subprocess.Popen | None:
    """启动进程:Windows 开新终端;Linux/Mac 优先 xterm/gnome-terminal,
    都没有则退化为 nohup 后台运行 + 日志落盘。"""
    try:
        if IS_WINDOWS:
            return subprocess.Popen(
                f'start "{name}" cmd /k "cd /d {cwd} && {cmd}"',
                shell=True,
                cwd=str(cwd),
            )
        for term in ("xterm", "gnome-terminal"):
            if shutil.which(term):
                return subprocess.Popen(
                    f'{term} -T "{name}" -e "cd {cwd} && {cmd}; read"',
                    shell=True,
                )
        # 无终端模拟器:后台运行,日志写到项目根(与旧版 backend_run.log 习惯一致)
        log_path = ROOT / f"{name}_run.log"
        with open(log_path, "a", encoding="utf-8") as logfile:
            return subprocess.Popen(
                cmd,
                shell=True,
                cwd=str(cwd),
                stdout=logfile,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except Exception as e:
        # 终端启动失败不该让整个入口崩掉；记录后继续（下方仍有信息输出）
        log(f"[ERROR] {name} 启动失败: {e}")
        return None


def cmd_start() -> None:
    log("=" * 50)
    log("  MathModelAgent - One-Click Start")
    log("=" * 50)
    log("")

    # 1. Check .env
    if not check_env():
        press_any_key("\n按任意键退出...")
        return

    # 2. Check backend port
    if check_port(BACKEND_PORT):
        log(f"[skip] backend already running on port {BACKEND_PORT}")
    else:
        log(f"[start] backend on http://127.0.0.1:{BACKEND_PORT}")
        # uvicorn 装在项目 .venv 里,不在系统 PATH 上;必须用 .venv 的 python -m 方式启动
        start_process(
            "backend",
            BACKEND_DIR,
            f'"{venv_python()}" -m uvicorn app.main:app --host 127.0.0.1 '
            f"--port {BACKEND_PORT} --workers 1 --limit-concurrency 64 "
            "--timeout-keep-alive 30",
        )
        log("  等待后端就绪...")
        for _ in range(10):
            time.sleep(2)
            if check_port(BACKEND_PORT):
                log("  [ ok ] backend ready")
                break
        else:
            log("  [warn] 后端可能还在启动中（首次需重建向量索引）")

    # 3. Check frontend port
    if check_port(FRONTEND_PORT):
        log(f"[skip] frontend already running on port {FRONTEND_PORT}")
    else:
        log(f"[start] frontend on http://localhost:{FRONTEND_PORT}")
        start_process("frontend", FRONTEND_DIR, "pnpm dev")

    log("")
    log("=" * 50)
    log(f"  Frontend : http://localhost:{FRONTEND_PORT}")
    log(f"  API docs : http://127.0.0.1:{BACKEND_PORT}/docs")
    log("=" * 50)
    log("")
    log("[tip] Docker 服务: docker compose up -d chromadb redis")
    press_any_key("按任意键关闭此窗口...")


# ── stop ───────────────────────────────────────────────────────────────


def _pids_on_port(port: str) -> set[int]:
    """跨平台查找监听指定端口的 PID 集合。探测工具缺失/失败时返回空集
    （停止操作必须永不抛异常——它常在出问题时被调用）。"""
    pids: set[int] = set()
    try:
        if IS_WINDOWS:
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, check=False
            ).stdout
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5 and parts[-1].isdigit():
                        pids.add(int(parts[-1]))
        else:
            lsof = shutil.which("lsof")
            if lsof:
                out = subprocess.run(
                    [lsof, "-ti", f"tcp:{port}"], capture_output=True, text=True, check=False
                ).stdout
                pids.update(int(p) for p in out.split() if p.isdigit())
            else:
                fuser = shutil.which("fuser")
                if fuser:
                    out = subprocess.run(
                        [fuser, f"{port}/tcp"], capture_output=True, text=True, check=False
                    ).stdout
                    pids.update(int(p) for p in out.split() if p.isdigit())
    except Exception:
        pass
    return pids


def _kill_pid(pid: int) -> None:
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            import os
            import signal

            os.kill(pid, signal.SIGTERM)
    except Exception:
        # 进程可能已自行退出；杀不到不算错误
        pass


def cmd_stop() -> None:
    log("Stopping MathModelAgent...")
    for port in (BACKEND_PORT, FRONTEND_PORT):
        pids = _pids_on_port(port)
        if not pids:
            log(f"[skip] port {port} 无监听进程")
            continue
        for pid in pids:
            log(f"[stop] port {port} PID {pid}")
            _kill_pid(pid)
    # POSIX 下 SIGTERM 是异步的,给一点时间再补刀
    if not IS_WINDOWS:
        time.sleep(1)
        for port in (BACKEND_PORT, FRONTEND_PORT):
            for pid in _pids_on_port(port):
                try:
                    import os
                    import signal

                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    # 已退出则无需补刀
                    pass
    # 容器化部署(compose 文件在项目根,不依赖容器名)
    if shutil.which("docker"):
        subprocess.run(
            ["docker", "compose", "down"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    log("Done.")


# ── 入口 ───────────────────────────────────────────────────────────────

USAGE = __doc__


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "start"
    flags = args[1:]

    if cmd in ("-h", "--help", "help"):
        log(USAGE)
        return
    if cmd == "install":
        cmd_install(use_docker="--docker" in flags)
        return
    if cmd == "start":
        cmd_start()
        return
    if cmd == "stop":
        cmd_stop()
        return
    log(f"[错误] 未知命令: {cmd}\n")
    log(USAGE)
    sys.exit(2)


if __name__ == "__main__":
    main()
