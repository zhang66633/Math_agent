"""编排器节点辅助层 — 从 nodes.py 抽出的纯辅助函数与哨兵异常（god-files 拆分 #31）。

节点函数本体仍在 nodes.py；本模块无节点依赖，可独立单测。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import threading
from pathlib import Path

from app.config import get_settings
from app.services.redis_pubsub import get_publisher

from .state import AgentState

logger = logging.getLogger(__name__)


class TaskCancelledError(Exception):
    """任务被取消时的哨兵异常 — 用于在节点内提前终止编排器。"""


# ── helper: publish node progress ────────────────────────────────────


def _pub_event(task_id: str, event: str, node: str, data: dict | None = None):
    """发布进度事件：实时推 Redis（WS 通道）+ 追加 JSONL（持久回放，dsh 式）。

    事件日志是前端"刷新不丢进度"的真相源：GET /api/tasks/{id}/events 回放。
    每个事件分配单调递增 seq（与 JSONL 行号对齐），Redis 信封与 JSONL 同值——
    前端据此对「WS 实时事件 vs REST 回放」幂等去重、断线后增量补拉（v2.2）。
    """
    seq = _next_event_seq(task_id)
    try:
        get_publisher().publish(task_id, event, node, data, seq=seq)
    except Exception:
        pass  # best-effort; never block the workflow on publish failures
    _log_event(task_id, event, node, data, seq=seq)


# ── helper: durable event log（session-as-source-of-truth，参考 dsh）──

_event_log_lock = threading.Lock()

# 每任务事件序号缓存（task_id → 已分配的最大 seq）
_event_seq: dict[str, int] = {}


def _event_log_path(task_id: str) -> Path:
    return get_settings().project_root / "data" / "task_events" / f"{task_id}.jsonl"


def _next_event_seq(task_id: str) -> int:
    """分配任务内单调递增的事件序号；首用按 JSONL 既有行数初始化。

    seq == 行号（第 n 条事件 seq=n），因此 GET /events?after=seq 即增量回放。
    仅正常追加场景保证严格对齐；损坏行被跳过时以返回值里的 seq 为准。
    """
    with _event_log_lock:
        last = _event_seq.get(task_id)
        if last is None:
            last = 0
            try:
                path = _event_log_path(task_id)
                if path.exists():
                    with open(path, encoding="utf-8") as f:
                        last = sum(1 for line in f if line.strip())
            except Exception:
                last = 0
        last += 1
        _event_seq[task_id] = last
        return last


def _log_event(
    task_id: str,
    event: str,
    node: str,
    data: dict | None = None,
    seq: int | None = None,
) -> None:
    """把进度事件追加到磁盘 JSONL（原子小写，best-effort 不阻塞工作流）。"""
    try:
        from app.services.redis_pubsub import ProgressEvent

        if seq is None:
            seq = _next_event_seq(task_id)
        msg = ProgressEvent(event=event, node=node, task_id=task_id, data=data, seq=seq)
        path = _event_log_path(task_id)
        with _event_log_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(msg.to_json() + "\n")
    except Exception:
        pass


def read_task_events(task_id: str, after: int = 0, limit: int = 500) -> tuple[list[dict], int]:
    """读取任务的持久化事件流（回放）。返回 (事件切片, 总条数)。"""
    events: list[dict] = []
    try:
        path = _event_log_path(task_id)
        if not path.exists():
            return [], 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return [], 0
    return events[after : after + limit], len(events)


# ── helper: per-tool timeout（chat 与 solution 两条通道共用）─────────


def tool_timeout(name: str) -> float:
    """每工具超时秒数。

    - web_search: 30s
    - run_code: 跟随沙箱执行预算（settings.sandbox_timeout）+ 20s 启动宽限。
      旧实现固定 60s，与沙箱自身预算同时到点：外层先报「工具执行超时」、
      沙箱线程继续后台跑完，两端口径不一致（审查 A5）。
    - 其余工具: 60s
    """
    if name == "web_search":
        return 30.0
    if name == "run_code":
        try:
            return float(get_settings().sandbox_timeout) + 20.0
        except Exception:
            return 200.0
    return 60.0


def parse_code_result(result_text: str) -> dict:
    """从 RunCodeTool 的输出文本中提取 stdout 和 images（chat/solution 共用）。"""
    stdout_parts: list[str] = []
    images: list[str] = []
    for line in (result_text or "").split("\n"):
        if line.startswith("输出:"):
            continue
        if line.startswith("生成图表:"):
            paths = line.replace("生成图表:", "").strip()
            images = [p.strip() for p in paths.split(",") if p.strip()]
        elif line.startswith("错误:"):
            continue
        else:
            stdout_parts.append(line)
    return {"stdout": "\n".join(stdout_parts).strip(), "images": images}


def tool_call_id(tc: dict, tool_name: str) -> str:
    """工具调用 id：优先 LLM 返回的 id，缺失时本地生成（保证 call/result 事件对可关联）。"""
    import uuid as _uuid

    return tc.get("id") or tc.get("tool_call_id") or f"{tool_name}-{_uuid.uuid4().hex[:8]}"


def get_cancel_event(task_id: str) -> threading.Event | None:
    """获取任务取消事件（供沙箱/工具执行中检查，事件级取消）。"""
    try:
        from app.services.session import get_session_manager

        return get_session_manager().get_cancel_event(task_id)
    except Exception:
        return None


def _is_cancelled(task_id: str) -> bool:
    """Check if the task has been cancelled."""
    try:
        from app.services.session import get_session_manager

        event = get_session_manager().get_cancel_event(task_id)
        return event.is_set()
    except Exception:
        return False


def _check_cancelled(task_id: str) -> None:
    """节点入口的取消检查：已取消则抛哨兵异常，让编排器提前退出。"""
    if _is_cancelled(task_id):
        raise TaskCancelledError(task_id)


def _save_working_memory(session_id: str, stage: str, output: str, extra: dict | None = None):
    """保存阶段检查点（WorkingMemory.save_checkpoint 会连带刷新问题状态文档）。

    历史教训：这里曾经分两步——检查点同步写、文档靠
    `asyncio.get_event_loop().run_in_executor(...)` 异步触发 LLM 整体重写。
    图节点跑在 langgraph 线程池 worker 里，那些线程没有运行中的事件循环，
    get_event_loop() 恒抛 RuntimeError 被静默跳过 → 文档在生产环境从未更新过
    （审计 2026-10-14 实证：所有真实任务的 problem_doc.md 都是初始模板），
    而 get_problem_doc() 当时零调用方。现在文档改成确定性拼装（读检查点 JSON、
    纯文件 IO、毫秒级），由 save_checkpoint 一并负责，同类 bug 不可能再出现。
    """
    try:
        from app.services.working_memory import WorkingMemory

        WorkingMemory(session_id).save_checkpoint(stage, output, extra)
    except Exception as e:  # noqa: BLE001
        # 工作记忆不阻塞主流程，但记录失败便于排查
        logger.warning(
            "工作记忆保存失败 (session=%s, stage=%s): %s",
            session_id,
            stage,
            e,
        )


# ============================================================
# 节点 1: 问题分类
# ============================================================
def _next_step(state: AgentState) -> int:
    """获取当前步骤索引并递增。"""
    return state.get("current_step_index", -1) + 1


def _collect_image_urls(text: str) -> list[str]:
    """从工具输出文本中提取 /api/images/... 形式的图表 URL（png/jpg/gif/webp）。

    去重保序：同一段文本里同一张图常出现两次（沙箱 stdout 打印一次、
    「生成图表:」清单再一次），实测事件流 tool_result.images 出现过
    `[q2_route.png, q2_route.png]`；不去重前端就会渲染两张一样的图。
    """
    return list(
        dict.fromkeys(
            re.findall(r"/api/images/[^\s,，)）'\"]+\.(?:png|jpg|jpeg|gif|webp)", text or "")
        )
    )


def _collect_file_urls(text: str, suffix: str) -> list[str]:
    """从工具输出文本中提取指定后缀的文件 URL（去重保序，理由同上）。"""
    pattern = rf"/api/task_files/[^\s,，)）'\"]+\.{suffix}"
    return list(dict.fromkeys(re.findall(pattern, text or "")))


def resolve_task_media_path(url: str) -> Path | None:
    """把 `/api/task_files/...` 或 `/api/images/...` URL 解析为本地文件路径。

    文件不存在 / URL 形态不认识一律返回 None。导出（DOCX 插图）与
    「论文引用了不存在的图」校验共用本实现——只有一份真源，
    否则导出与校验会各说各话（导出插得上、校验说没有）。

    `/api/images/{run_id}/{name}` 是沙箱临时目录链接，先查 temp，
    再回退持久副本 `data/chat_images/{run_id}/`（temp 会被系统清理）。
    """
    settings = get_settings()
    parts = (url or "").rstrip("/").split("/")
    try:
        if "task_files" in parts:
            # /api/task_files/{task_id}/{filename}
            task_id = parts[parts.index("task_files") + 1]
            filename = parts[-1]
            p = settings.project_root / "data" / "task_files" / task_id / filename
            return p if p.exists() else None
        if "images" in parts:
            run_id = parts[parts.index("images") + 1]
            filename = parts[-1]
            for p in (
                Path(tempfile.gettempdir()) / "mathmodel_outputs" / run_id / filename,
                settings.project_root / "data" / "chat_images" / run_id / filename,
            ):
                if p.exists():
                    return p
    except (ValueError, IndexError):
        return None
    return None


# 独立成行的图片引用（与 md_docx 的插图判定同一形态）
_MD_IMAGE_LINE_RE = re.compile(r"^!\[[^\]]*\]\((/api/(?:task_files|images)/[^)\s]+)\)$")
# 图注行：`图 4.1：…` / `Figure 3 …`
_FIGURE_CAPTION_RE = re.compile(r"^\s*(?:图|figure)\s*\d", re.IGNORECASE)


def strip_missing_image_refs(markdown: str) -> tuple[str, list[str]]:
    """删掉指向**不存在文件**的图片引用行，返回 (清理后的 markdown, 被删的 URL)。

    为什么必须做：写作节点会臆造图片链接（实测任务 12df70f4：论文引用了
    `/api/task_files/12df70f4/q4_pareto--8f3a1c.png`，而该文件在求解/验证
    材料与文件区里都不存在）。后果有两处，都发生在**交付物**上：
      · 网页阅读器里是一张破图；
      · DOCX 导出时解析不到本地文件 → 这一行原样落成正文文字
        （`![图3](/api/task_files/...)`），评委翻开就是一行源码。

    处理：整行删除；紧跟其后的图注（`图 X：…`）一并删除，避免出现
    「有图注没图」的悬空描述。返回被删 URL 供调用方打日志/告警。
    """
    if not markdown:
        return markdown, []
    lines = markdown.split("\n")
    kept: list[str] = []
    dropped: list[str] = []
    i = 0
    while i < len(lines):
        m = _MD_IMAGE_LINE_RE.match(lines[i].strip())
        if m and resolve_task_media_path(m.group(1)) is None:
            dropped.append(m.group(1))
            i += 1
            # 跳过紧随其后的空行与图注行
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and _FIGURE_CAPTION_RE.match(lines[i]):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    if dropped:
        logger.warning("论文引用了不存在的图片，已移除引用：%s", dropped)
        return "\n".join(kept), dropped
    return markdown, []


def count_paper_structure(markdown: str) -> tuple[int, int]:
    """统计论文正文结构：返回 (章数, 图片引用数)。

    用于 node_end 事件给前端报「几章 / 几张图」——比「输出 4 万字」
    对读者有意义（字数在气泡里是噪音，已在前端文案层禁止）。

    章只数**二级标题**（`## `）：三级标题是小节，混进来会把真实结构报错。
    实测 E2E 任务 d20f5bee 的论文是 `## × 9 + ### × 41`，两者相加就成了
    「50 章」——数字看着不难看，但是**错的**，而错的数字比没有数字更糟。
    一级标题是论文题目本身，同样不计。
    """
    if not markdown:
        return 0, 0
    sections = len(re.findall(r"^##\s+\S", markdown, flags=re.MULTILINE))
    figures = len(re.findall(r"!\[[^\]]*\]\([^)]*\)", markdown))
    return sections, figures



def _persist_task_files(
    task_id: str,
    image_urls: list[str] = (),
    xlsx_urls: list[str] = (),
    csv_urls: list[str] = (),
    html_urls: list[str] = (),
) -> dict[str, list[str]]:
    """把沙箱临时目录里的所有文件复制到任务持久目录，并登记进文件区。

    返回持久化后的各类 URL 列表。
    """
    from app.services.session import get_session_manager

    settings = get_settings()
    task_dir = settings.project_root / "data" / "task_files" / task_id
    temp_root = Path(tempfile.gettempdir()) / "mathmodel_outputs"
    session_mgr = get_session_manager()

    def _persist(urls: list[str], file_type: str) -> tuple[list[str], dict[str, str]]:
        durable: list[str] = []
        url_map: dict[str, str] = {}
        for url in urls:
            try:
                parts = url.rstrip("/").split("/")
                run_id_or_task_id, filename = parts[-2], parts[-1]
                src = temp_root / run_id_or_task_id / filename
                if not src.exists():
                    # 也可能在 task_files 目录
                    src = task_dir / filename
                if not src.exists():
                    continue
                task_dir.mkdir(parents=True, exist_ok=True)
                # 内容 hash 命名（审查 B4）：多轮重跑常产出同名 figure_1.png
                # 但内容不同；旧实现 dst.exists() 即跳过 + url_map 仍映射到
                # 同一持久 URL → 报告两处引用同一 URL（重复渲染）且内容是
                # 第一轮旧图。hash 后同名不同内容天然分文件，同内容天然去重。
                import hashlib as _hashlib

                try:
                    digest = _hashlib.md5(src.read_bytes()).hexdigest()[:8]
                except Exception:
                    digest = "nohash"
                stem = Path(filename).stem[:40]
                suffix = Path(filename).suffix
                durable_name = f"{stem}--{digest}{suffix}" if digest != "nohash" else filename
                dst = task_dir / durable_name
                if not dst.exists():
                    shutil.copy2(src, dst)
                durable_url = f"/api/task_files/{task_id}/{durable_name}"
                session_mgr.add_artifact(
                    task_id,
                    {
                        "type": file_type,
                        "name": durable_name,
                        "url": durable_url,
                        "size": dst.stat().st_size,
                    },
                )
                durable.append(durable_url)
                # 旧临时 URL（/api/images/{run_id}/... 或 /api/task_files/{run_id}/...）
                # → 持久 URL 映射，供最终报告整体改写（审查 P1：图片链接生命周期）
                url_map[url] = durable_url
            except Exception:  # noqa: BLE001
                continue
        return durable, url_map

    images, map_i = _persist(image_urls, "figure")
    xlsx, map_x = _persist(xlsx_urls, "xlsx")
    csv, map_c = _persist(csv_urls, "csv")
    html, map_h = _persist(html_urls, "html")
    return {
        "images": images,
        "xlsx": xlsx,
        "csv": csv,
        "html": html,
        "url_map": {**map_i, **map_x, **map_c, **map_h},
    }


def _persist_task_images(task_id: str, image_urls: list[str]) -> list[str]:
    """把沙箱临时目录里的图表复制到任务持久目录，并登记进文件区。

    返回持久化后的 /api/task_files/{task_id}/{filename} URL 列表。
    """
    return _persist_task_files(task_id, image_urls=image_urls)["images"]


def _extract_code_block(text: str) -> str:
    """从 LLM 输出中提取 Python 代码块。"""
    import re

    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 如果没有代码块标记，返回空（避免执行非代码内容）
    return ""


def _clean_md(text: str) -> str:
    """去掉 LLM 输出外层的 Markdown 代码块标记。"""
    text = str(text)
    text = re.sub(r"^```(?:markdown|md)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


def _extract_json(text: str) -> dict | list:
    """从 LLM 输出中提取 JSON。"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取 { } 或 [ ]
    for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue

    return {}


def _log_usage(task_id: str, node: str, response) -> None:
    """记录一次 LLM 调用的 token 用量（管线成本可观测性）。

    response 可以是 AIMessage（取 usage_metadata）或流式返回的 usage dict。
    """
    try:
        usage = getattr(response, "usage_metadata", None)
        if not usage and isinstance(response, dict):
            usage = response
        if usage:
            logger.info(
                "LLM 用量 [%s/%s]: in=%s out=%s total=%s",
                task_id,
                node,
                usage.get("input_tokens"),
                usage.get("output_tokens"),
                usage.get("total_tokens"),
            )
    except Exception:
        pass  # 用量缺失不影响主流程


# 瞬时链路错误的特征。这类错误重试有意义，且**流式路径更容易踩到**：
# 分块传输被中间层/代理破坏时，会出现 `zstd decompressor error: Unknown frame descriptor`
# 之类的解码失败（实测：网络抖动期间方案模式整个任务 error，而同一时刻非流式调用正常）。
_TRANSIENT_ERROR_MARKERS = (
    "zstd",
    "zstandard",
    "decodingerror",
    "remoteprotocolerror",
    "connectionerror",
    "connecterror",
    "connection reset",
    "connection aborted",
    "readtimeout",
    "read error",
    "incompleteread",
    "incomplete read",
    "peer closed",
    "server disconnected",
    "temporarily unavailable",
    "timed out",
    "timeout",
    "429",
    "502",
    "503",
    "504",
)


def _is_transient_error(exc: Exception) -> bool:
    """判断是否为瞬时链路错误（网络抖动 / 响应解码失败 / 限流 / 网关错误）。"""
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _TRANSIENT_ERROR_MARKERS)


def invoke_with_retry(llm, messages, task_id: str = "", node: str = "", retries: int = 2):
    """LLM 调用统一重试：抗 API 抖动、429、超时等瞬时故障。

    瞬时链路错误给更长的退避（1s/2s → 3s/6s）：网络抖动往往需要数秒才能恢复，
    按原来的短间隔重试等于把重试额度一次性烧光。确定性错误（如 API Key 无效）
    重试后仍会抛出，错误照常上浮。
    """
    import time as _time

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return llm.invoke(messages)
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt >= retries:
                break
            delay = (3, 6, 12)[attempt] if _is_transient_error(e) else 2**attempt
            logger.warning(
                "LLM 调用失败 [%s/%s] 第 %d 次（瞬时=%s），%.0fs 后重试: %s",
                task_id,
                node or "llm",
                attempt + 1,
                _is_transient_error(e),
                delay,
                str(e)[:200],
            )
            _time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def invoke_streaming_with_retry(
    llm,
    messages,
    task_id: str = "",
    node: str = "",
    retries: int = 2,
    throttle_ms: int = 100,
):
    """流式 LLM 调用（dsh 式方案模式流式输出）。

    - 同步 llm.stream() 逐 chunk 提取文本增量，节流推送 node_delta 事件
      （前端像 chat 一样逐字渲染节点输出，而不是完成后跳一个摘要块）
    - 失败指数退避重试（与 invoke_with_retry 一致）
    - 返回 (完整文本, usage_metadata dict) 供 _log_usage 计量
    """
    import time as _time

    # 闭包与状态在循环外定义（避免 ruff B023 循环变量绑定）
    full: list[str] = []
    buf: list[str] = []
    last_emit = [0.0]

    def _flush() -> None:
        if buf:
            _pub_event(task_id, "node_delta", node, {"delta": "".join(buf)})
            buf.clear()
        last_emit[0] = _time.monotonic()

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            # 重试前发 reset：前端清空已收到的增量，避免失败流与重试流文本重复/乱序
            if attempt > 0:
                _pub_event(task_id, "node_delta", node, {"reset": True})
            full.clear()
            buf.clear()
            last_emit[0] = 0.0
            usage_meta: dict = {}

            for chunk in llm.stream(messages):
                delta = getattr(chunk, "content", None)
                if isinstance(delta, list):
                    delta = "".join(
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in delta
                    )
                if not delta:
                    # 无文本的 chunk 可能携带 usage（OpenAI 流末帧）
                    u = getattr(chunk, "usage_metadata", None)
                    if u:
                        usage_meta = dict(u)
                    continue
                full.append(delta)
                buf.append(delta)
                now = _time.monotonic()
                if now - last_emit[0] >= throttle_ms / 1000 or len("".join(buf)) >= 64:
                    _flush()
            _flush()
            return "".join(full), usage_meta
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt >= retries:
                break
            delay = (3, 6, 12)[attempt] if _is_transient_error(e) else 2**attempt
            logger.warning(
                "LLM 流式调用失败 [%s/%s] 第 %d 次（瞬时=%s），%.0fs 后重试: %s",
                task_id,
                node or "llm",
                attempt + 1,
                _is_transient_error(e),
                delay,
                str(e)[:200],
            )
            _time.sleep(delay)

    # 流式路径对链路质量更敏感（分块传输被中间层破坏 → zstd/解码失败）。重试耗尽且
    # 属瞬时错误时，用一次**非流式**调用兜底：任务能完成比逐字动画重要，
    # 拿到的完整内容仍会推给前端（前端收到一次 reset + 整段 delta）。
    if last_exc is not None and _is_transient_error(last_exc):
        try:
            logger.warning(
                "流式路径不可用，降级为非流式调用 [%s/%s]: %s",
                task_id,
                node or "llm",
                str(last_exc)[:160],
            )
            _pub_event(task_id, "node_delta", node, {"reset": True})
            resp = llm.invoke(messages)
            text = getattr(resp, "content", "") or ""
            if isinstance(text, list):
                text = "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in text
                )
            if text:
                _pub_event(task_id, "node_delta", node, {"delta": str(text)})
                return str(text), dict(getattr(resp, "usage_metadata", None) or {})
        except Exception as fallback_exc:  # noqa: BLE001
            logger.warning(
                "非流式兜底同样失败 [%s/%s]: %s", task_id, node or "llm", str(fallback_exc)[:160]
            )

    raise last_exc  # type: ignore[misc]


# ── helper: 执行计划解析（planner 输出 → 步骤 + 理由）────────────────

_VALID_PLAN_STEPS = {
    "analysis",
    "modeling",
    "data_preprocessing",
    "solving",
    "verification",
    "export_results",
    "writing",
}
_DEFAULT_PLAN = ["analysis", "modeling", "solving", "verification", "writing"]


def parse_execution_plan(plan_json) -> tuple[list[str], dict[str, str]]:
    """解析 planner 输出为 (步骤列表, 步骤→理由)。

    兼容两种格式：
      - 新格式：``[{"step": "analysis", "reason": "..."}, ...]``（v2.2，带理由）
      - 旧格式：``["analysis", "modeling", ...]``（reason 缺省为空）

    白名单过滤（幻觉步骤名会让路由静默跳到收尾）+ 去重保序 +
    程序化修正：首步必须 analysis、末步必须 writing；剔空回退默认计划。
    """
    steps: list[str] = []
    reasons: dict[str, str] = {}
    if isinstance(plan_json, list):
        for item in plan_json:
            if isinstance(item, str):
                s = item.strip()
                if s:
                    steps.append(s)
            elif isinstance(item, dict):
                s = str(item.get("step", "")).strip()
                if s:
                    steps.append(s)
                    r = str(item.get("reason", "")).strip()
                    if r:
                        reasons[s] = r
    cleaned = [s for s in dict.fromkeys(steps) if s in _VALID_PLAN_STEPS]
    if not cleaned:
        cleaned = list(_DEFAULT_PLAN)
    if cleaned[0] != "analysis":
        cleaned.insert(0, "analysis")
    if cleaned[-1] != "writing":
        cleaned.append("writing")
    return cleaned, reasons


def _clip_head_tail(text: str, limit: int) -> str:
    """头尾保留截断：LLM 输出的结论/判定块通常在文末，纯保头会切掉关键信息。

    头 60% + 尾 40%，中间用省略标记衔接。
    """
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    head = int(limit * 0.6)
    tail = limit - head
    return f"{text[:head]}\n…（中间省略 {len(text) - limit} 字符）…\n{text[-tail:]}"


def build_verification_feedback(full_text: str, ver_json: dict) -> str:
    """构造回退时给建模/求解节点的修正反馈（审查 C3）。

    旧实现取 full_text[:500]——而验证 prompt 要求 JSON 判定块在**末尾**，
    关键问题清单（critical_issues）恰好被切掉，回退修正只能拿到开头套话。
    改为：判定块字段优先（verdict/rollback_target/critical_issues），
    判定块无问题清单时退回正文头尾摘录。
    """
    lines: list[str] = []
    verdict = str(ver_json.get("verdict", "")).strip().upper()
    if verdict:
        lines.append(f"判定: {verdict}")
    if ver_json.get("rollback_target"):
        lines.append(f"回退目标: {ver_json['rollback_target']}")
    issues = ver_json.get("critical_issues") or ver_json.get("issues") or []
    if isinstance(issues, str):
        issues = [issues]
    if issues:
        for i, iss in enumerate(issues, 1):
            lines.append(f"{i}. {str(iss).strip()}")
    else:
        lines.append("（验证未给出具体问题清单，以下为验证正文头尾摘录）")
        lines.append(_clip_head_tail(full_text, 800))
    return "\n".join(lines)[:1500]


def _extract_verdict_json(text: str) -> dict:
    """从验证节点输出提取含 verdict 的判定 JSON（容忍前后散文、嵌套、围栏）。

    替代旧的正则 `\\{[^{}]*"verdict"...\\}`（嵌套/跨行即失败）：
    先复用 _extract_json，失败时定位第一个含 "verdict" 的平衡花括号块。
    """
    parsed = _extract_json(str(text))
    if isinstance(parsed, dict) and "verdict" in parsed:
        return parsed

    text = str(text)
    start = text.find('"verdict"')
    if start < 0:
        return {}
    brace = text.rfind("{", 0, start)
    if brace < 0:
        return {}
    depth = 0
    for i in range(brace, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[brace : i + 1])
                    return obj if isinstance(obj, dict) else {}
                except json.JSONDecodeError:
                    return {}
    return {}
