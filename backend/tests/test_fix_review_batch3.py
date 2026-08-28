"""审查修复批次三回归测试 — 超时/重复图表/思考过程三主题的修复锚点。

覆盖:
  - 事件 seq：单调递增、JSONL 与 publisher 同值（前端幂等去重的依据）
  - parse_execution_plan：新格式 [{step,reason}] / 旧格式 / 幻觉步骤 / 去重
  - _clip_head_tail / build_verification_feedback：验证反馈不再砍头丢结论
  - _persist_task_files：内容 hash 命名，同名不同内容分文件、同内容去重
  - SandboxExecutor subprocess 超时：回传部分 stdout
  - RunCodeTool：失败无条件输出错误段（stderr 为空也不吞）
"""

from __future__ import annotations

from app.core import node_helpers
from app.core.node_helpers import (
    _clip_head_tail,
    _log_event,
    _persist_task_files,
    _pub_event,
    build_verification_feedback,
    parse_execution_plan,
    read_task_events,
)

# ── 事件 seq ──────────────────────────────────────────────────────


class _SeqCapturePublisher:
    def __init__(self):
        self.events: list[dict] = []

    def publish(self, task_id, event, node, data=None, seq=None):
        self.events.append({"event": event, "seq": seq})
        return 1


def test_pub_event_assigns_monotonic_seq(tmp_path, monkeypatch):
    """_pub_event 分配任务内单调递增 seq，Redis 信封与 JSONL 同值。"""
    monkeypatch.setattr(node_helpers, "_event_log_path", lambda tid: tmp_path / f"{tid}.jsonl")
    monkeypatch.setattr(node_helpers, "_event_seq", {})  # 清进程级缓存防跨文件串号
    cap = _SeqCapturePublisher()
    monkeypatch.setattr(node_helpers, "get_publisher", lambda: cap)

    _pub_event("tsk", "node_start", "classify_problem", {"step": 1})
    _pub_event("tsk", "node_end", "classify_problem", {"step": 1})
    _pub_event("tsk", "plan", "plan_execution", {"plan": ["analysis"]})

    assert [e["seq"] for e in cap.events] == [1, 2, 3]
    events, total = read_task_events("tsk")
    assert total == 3
    assert [e["seq"] for e in events] == [1, 2, 3]


def test_pub_event_seq_continues_from_existing_log(tmp_path, monkeypatch):
    """进程重启（内存 seq 丢失）后按 JSONL 行数续号，不回退。"""
    monkeypatch.setattr(node_helpers, "_event_log_path", lambda tid: tmp_path / f"{tid}.jsonl")
    cap = _SeqCapturePublisher()
    monkeypatch.setattr(node_helpers, "get_publisher", lambda: cap)
    monkeypatch.setattr(node_helpers, "_event_seq", {})  # 模拟冷启动

    _log_event("tsk2", "node_start", "analysis_agent", seq=1)
    _log_event("tsk2", "node_end", "analysis_agent", seq=2)

    _pub_event("tsk2", "node_start", "modeling_agent")
    events, _ = read_task_events("tsk2")
    assert [e["seq"] for e in events] == [1, 2, 3]
    assert cap.events[0]["seq"] == 3


def test_seq_isolated_per_task(tmp_path, monkeypatch):
    """不同任务 seq 独立计数。"""
    monkeypatch.setattr(node_helpers, "_event_log_path", lambda tid: tmp_path / f"{tid}.jsonl")
    monkeypatch.setattr(node_helpers, "_event_seq", {})  # 清进程级缓存防跨文件串号
    cap = _SeqCapturePublisher()
    monkeypatch.setattr(node_helpers, "get_publisher", lambda: cap)

    _pub_event("a", "node_start", "classify_problem")
    _pub_event("b", "node_start", "classify_problem")
    _pub_event("a", "node_end", "classify_problem")
    assert cap.events[0]["seq"] == 1
    assert cap.events[1]["seq"] == 1
    assert cap.events[2]["seq"] == 2


# ── 执行计划解析（planner 理由）────────────────────────────────────


def test_parse_plan_new_format_with_reasons():
    plan, reasons = parse_execution_plan(
        [
            {"step": "analysis", "reason": "多目标问题需先拆解"},
            {"step": "modeling", "reason": "评价类问题"},
            {"step": "writing"},
        ]
    )
    # 首步 analysis / 末步 writing 已满足 → 不额外插入步骤；
    # 评价类无求解步是合法计划
    assert plan == ["analysis", "modeling", "writing"]
    assert reasons["analysis"] == "多目标问题需先拆解"
    assert "writing" not in reasons  # 无 reason 的步骤不产生空串条目


def test_parse_plan_legacy_string_array():
    plan, reasons = parse_execution_plan(["analysis", "modeling", "solving", "verification"])
    assert plan == ["analysis", "modeling", "solving", "verification", "writing"]
    assert reasons == {}


def test_parse_plan_hallucinated_steps_dropped():
    plan, _ = parse_execution_plan(
        [
            {"step": "analysis", "reason": "r"},
            {"step": "magic_agent", "reason": "幻觉"},
            {"step": "solving"},
        ]
    )
    assert "magic_agent" not in plan
    assert plan == ["analysis", "solving", "writing"]


def test_parse_plan_empty_falls_back_to_default():
    plan, _ = parse_execution_plan("not-a-list")
    assert plan == ["analysis", "modeling", "solving", "verification", "writing"]


def test_parse_plan_dedupes_repeated_steps():
    plan, _ = parse_execution_plan(
        [{"step": "analysis"}, {"step": "solving"}, {"step": "solving"}]
    )
    assert plan.count("solving") == 1


# ── 验证反馈（思考过程准确性）──────────────────────────────────────


def test_clip_head_tail_short_noop():
    assert _clip_head_tail("短文本", 100) == "短文本"


def test_clip_head_tail_keeps_tail():
    text = "HEAD" + "x" * 400 + "TAIL-CONCLUSION"
    out = _clip_head_tail(text, 100)
    assert out.startswith("HEAD")
    assert "TAIL-CONCLUSION" in out
    assert "中间省略" in out


def test_verification_feedback_prefers_critical_issues():
    full = "分析开头……" + "y" * 3000 + '\n```json\n{"verdict": "FAIL", "rollback_target": "modeling", "critical_issues": ["约束遗漏", "目标函数量纲不一致"]}\n```'
    fb = build_verification_feedback(
        full, {"verdict": "FAIL", "rollback_target": "modeling", "critical_issues": ["约束遗漏", "目标函数量纲不一致"]}
    )
    assert "判定: FAIL" in fb
    assert "回退目标: modeling" in fb
    assert "约束遗漏" in fb and "目标函数量纲不一致" in fb


def test_verification_feedback_fallback_excerpt_includes_tail():
    """判定块无问题清单时退回正文头尾摘录——尾部结论不能丢。"""
    text = "开头分析 " + "z" * 2000 + " 最终结论：模型约束缺失。"
    fb = build_verification_feedback(text, {"verdict": "FAIL"})
    assert "最终结论：模型约束缺失。" in fb
    assert len(fb) <= 1500


# ── 持久化 hash 命名（图表重复 B4）─────────────────────────────────


class _StubSessionMgr:
    def __init__(self):
        self.artifacts: list[dict] = []

    def add_artifact(self, task_id, artifact):
        self.artifacts.append(artifact)


def _setup_persist_env(tmp_path, monkeypatch):
    import tempfile as _tempfile

    monkeypatch.setattr(_tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    (tmp_path / "tmp" / "mathmodel_outputs" / "run1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tmp" / "mathmodel_outputs" / "run2").mkdir(parents=True, exist_ok=True)

    # project_root 是 property，实例不可 setattr —— 打类级 property
    from app.config import Settings, get_settings

    monkeypatch.setattr(
        Settings, "project_root", property(lambda self: tmp_path), raising=False
    )
    _ = get_settings()  # 确保单例在打桩后使用新 property

    stub = _StubSessionMgr()
    import app.services.session as session_mod

    monkeypatch.setattr(session_mod, "get_session_manager", lambda: stub)
    return stub


def test_persist_same_name_different_content_split(tmp_path, monkeypatch):
    """两轮 run 同名 figure_1.png 但内容不同 → 两个不同持久 URL（旧图不再顶新图）。"""
    _setup_persist_env(tmp_path, monkeypatch)
    (tmp_path / "tmp" / "mathmodel_outputs" / "run1" / "figure_1.png").write_bytes(b"round-one")
    (tmp_path / "tmp" / "mathmodel_outputs" / "run2" / "figure_1.png").write_bytes(b"round-two")

    out1 = _persist_task_files("tk", image_urls=["/api/images/run1/figure_1.png"])
    out2 = _persist_task_files("tk", image_urls=["/api/images/run2/figure_1.png"])

    assert out1["images"] != out2["images"]
    assert out1["url_map"]["/api/images/run1/figure_1.png"] != out2["url_map"][
        "/api/images/run2/figure_1.png"
    ]


def test_persist_identical_content_dedupes(tmp_path, monkeypatch):
    """同内容多轮 → 同一持久 URL（天然去重）。"""
    _setup_persist_env(tmp_path, monkeypatch)
    (tmp_path / "tmp" / "mathmodel_outputs" / "run1" / "figure_1.png").write_bytes(b"same")
    (tmp_path / "tmp" / "mathmodel_outputs" / "run2" / "figure_1.png").write_bytes(b"same")

    out1 = _persist_task_files("tk", image_urls=["/api/images/run1/figure_1.png"])
    out2 = _persist_task_files("tk", image_urls=["/api/images/run2/figure_1.png"])
    assert out1["images"] == out2["images"]


# ── 沙箱超时回传部分输出 ──────────────────────────────────────────


def test_subprocess_timeout_returns_partial_stdout(tmp_path, monkeypatch):
    """超时被杀后，stdout 保留已打印内容 + stderr 说明超时（审查 A3）。"""
    from app.sandbox.executor import SandboxExecutor

    ex = SandboxExecutor(timeout=2)
    ex.backend = "subprocess"  # 测试机可能有 docker，强制 subprocess 路径
    result = ex.run(
        "import sys\nprint('PARTIAL-RESULT-12345', flush=True)\n"
        "import time\ntime.sleep(60)\nprint('NEVER-REACHED')"
    )
    assert result["success"] is False
    assert "PARTIAL-RESULT-12345" in result["stdout"]
    assert "NEVER-REACHED" not in result["stdout"]
    assert "超时" in result["stderr"]


def test_run_code_failure_always_reports_error(tmp_path, monkeypatch):
    """失败 + stderr 为空也必须输出错误段（returncode 兜底，审查 A）。"""
    from app.config import get_settings
    from app.tools.interaction_tools import RunCodeTool

    monkeypatch.setattr(get_settings(), "sandbox_timeout", 5)
    monkeypatch.setattr(get_settings(), "sandbox_backend", "subprocess")

    tool = RunCodeTool()
    # flush=True：os._exit 跳过缓冲区刷新，不 flush 的 print 会整段丢失
    text = tool._run(code="print('partial-out', flush=True)\nimport os\nos._exit(3)")
    assert "错误:" in text
    assert "partial-out" in text
    assert "returncode=3" in text
