"""Data preprocessing agent node - cleaning, feature engineering, charts.

Split from core/nodes.py: nodes.py keeps only orchestration nodes
(classify/retrieve/plan/format_response) plus re-exports.
"""

from __future__ import annotations

import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.state import AgentState
from app.tools.interaction_tools import RunCodeTool
from app.tools.math_tools import create_math_tools

from ..llm.factory import get_llm
from ..node_helpers import (
    _check_cancelled,
    _collect_image_urls,
    _log_usage,
    _next_step,
    _persist_task_files,
    _pub_event,
    _save_working_memory,
    get_cancel_event,
    invoke_with_retry,
    parse_code_result,
    tool_call_id,
    tool_timeout,
)
from ..prompts.preprocessing import (
    PREPROCESSING_SYSTEM_PROMPT,
    PREPROCESSING_USER_TEMPLATE,
)


def data_preprocessing_agent_node(state: AgentState) -> dict:
    """数据预处理 Agent — 独立 EDA 和数据清洗节点。

    仅在 execute 模式且有数据文件时执行。
    - 多轮 tool loop 调用 run_code 完成数据质量检查、统计摘要、可视化
    - 产出结构化 EDA 报告供后续 modeling/solving 使用
    """
    idx = _next_step(state)
    task_id = state["session_id"]
    _check_cancelled(task_id)

    # 无数据文件时跳过
    data_files = state.get("data_files") or []
    if not data_files and not state.get("data_files_dir"):
        _pub_event(
            task_id,
            "node_end",
            "data_preprocessing_agent",
            {
                "step": idx + 1,
                "skipped": True,
                "summary": "无数据文件，跳过数据预处理",
                "title": "数据预处理",
                "desc": "（无数据，已跳过）",
            },
        )
        return {
            "preprocessed_data": None,
            "current_step_index": idx,
            "messages": [SystemMessage(content=f"[预处理Agent] 第{idx + 1}步跳过（无数据文件）")],
        }

    _pub_event(task_id, "node_start", "data_preprocessing_agent", {"step": idx + 1})
    llm = get_llm("solving", state.get("api_key_config"))  # 复用 solving 的 LLM 配置

    # 注入数据文件目录
    run_code_tool = RunCodeTool()
    run_code_tool.data_files_dir = state.get("data_files_dir", "")

    tools = [run_code_tool] + create_math_tools()
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    model_text = state.get("model_output") or "无模型"

    # 构建数据文件上下文
    data_files_context = ""
    if data_files:
        lines = ["\n## 可用数据文件（已挂载到工作目录，代码中直接用文件名读取）"]
        for df in data_files:
            lines.append(
                f"- `{df.get('filename', '?')}`: "
                f"{df.get('rows', '?')}行, "
                f"列: {', '.join(df.get('columns', []))}"
            )
        data_files_context = "\n".join(lines)

    system_prompt = PREPROCESSING_SYSTEM_PROMPT
    user_prompt = PREPROCESSING_USER_TEMPLATE.format(
        problem=state["problem_raw"],
        model=model_text,
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt + data_files_context),
    ]

    all_images: list[str] = []
    max_rounds = 5

    for _ in range(max_rounds):
        _check_cancelled(task_id)
        response = invoke_with_retry(
            llm_with_tools, messages, task_id=task_id, node="preprocessing_tool"
        )
        _log_usage(task_id, "preprocessing_tool", response)
        messages.append(response)
        # 每轮 LLM 解说文本推给前端（与流式节点的 node_delta 同通道，逐轮累积）
        round_text = getattr(response, "content", "") or ""
        if round_text:
            _pub_event(
                task_id,
                "node_delta",
                "data_preprocessing_agent",
                {"delta": str(round_text)},
            )

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break

        # 协议 v2.1：tool_call（running）→ 执行 → tool_result（id 回声，同一卡片两段更新）
        for tc in tool_calls:
            _pub_event(
                task_id,
                "tool_call",
                "data_preprocessing_agent",
                {
                    "tool_call_id": tool_call_id(tc, tc.get("name")),
                    "tool_name": tc.get("name"),
                    "input": {
                        k: (str(v)[:1500] if k == "code" else v)
                        for k, v in (tc.get("args") or {}).items()
                    },
                    "status": "running",
                },
            )

        def _run_one(tc: dict) -> tuple[str, dict]:
            """执行单个工具，返回 (结果文本, 元信息)。"""
            tool_name = tc.get("name")
            tool_args = tc.get("args") or {}
            tool = tool_map.get(tool_name)
            t0 = time.monotonic()
            if tool is None:
                return (
                    f"未知工具: {tool_name}",
                    {
                        "tool_name": tool_name,
                        "ok": False,
                        "error": f"未知工具: {tool_name}",
                        "duration_ms": 0,
                    },
                )
            try:
                text = tool.invoke(tool_args)
                return text, {
                    "tool_name": tool_name,
                    "ok": True,
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                }
            except Exception as e:  # noqa: BLE001
                return (
                    f"工具执行失败: {e}",
                    {
                        "tool_name": tool_name,
                        "ok": False,
                        "error": str(e)[:200],
                        "duration_ms": int((time.monotonic() - t0) * 1000),
                    },
                )

        from concurrent.futures import ThreadPoolExecutor

        results: dict[str, tuple[str, dict]] = {}

        # run_code 串行（取消事件注入）；其余工具并行 + 超时
        run_code_tool.cancel_event = get_cancel_event(task_id)
        for tc in tool_calls:
            if tc.get("name") != "run_code":
                continue
            tc_id = tool_call_id(tc, "run_code")
            _pub_event(task_id, "code_exec", "data_preprocessing_agent", {"status": "running", "id": tc_id})
            text, meta = _run_one(tc)
            results[tc_id] = (text, meta)
            code_data = parse_code_result(text)
            _pub_event(
                task_id,
                "code_exec",
                "data_preprocessing_agent",
                {
                    "status": "done",
                    "id": tc_id,
                    **code_data,
                    "ok": meta["ok"],
                    "duration_ms": meta["duration_ms"],
                },
            )

        others = [tc for tc in tool_calls if tc.get("name") != "run_code"]
        if others:
            # 不用 with：__exit__ 的 shutdown(wait=True) 会无限 join 已超时放弃的
            # 卡死线程，把整个编排器拖住（审查 P1「超时是假象」）。
            # wait=False 立即返回；cancel_futures 取消队列里尚未开跑的任务。
            _pool = ThreadPoolExecutor(max_workers=min(4, len(others)))
            try:
                _futs: dict[str, tuple] = {
                    tool_call_id(tc, tc.get("name")): (_pool.submit(_run_one, tc), tc.get("name"))
                    for tc in others
                }
                for tc_id, (_fut, tool_name) in _futs.items():
                    try:
                        text, meta = _fut.result(timeout=tool_timeout(tool_name))
                    except TimeoutError:
                        text = f"工具执行超时（{tool_timeout(tool_name):.0f}s）"
                        meta = {
                            "tool_name": tool_name,
                            "ok": False,
                            "error": text,
                            "duration_ms": int(tool_timeout(tool_name) * 1000),
                        }
                    results[tc_id] = (text, meta)
            finally:
                _pool.shutdown(wait=False, cancel_futures=True)

        for tc in tool_calls:
            tc_id = tool_call_id(tc, tc.get("name"))
            tool_name = tc.get("name")
            text, meta = results[tc_id]

            if tool_name == "run_code":
                all_images.extend(_collect_image_urls(text))

            _pub_event(
                task_id,
                "tool_result",
                "data_preprocessing_agent",
                {
                    "tool_call_id": tc_id,
                    "tool_name": tool_name,
                    "preview": text[:1500],
                    "ok": meta["ok"],
                    "duration_ms": meta["duration_ms"],
                    "images": _collect_image_urls(text),
                    **({"error": meta["error"]} if meta.get("error") else {}),
                },
            )

            messages.append(
                ToolMessage(
                    content=text,
                    tool_call_id=tc_id,
                )
            )

    # 最终输出 = 最后一条 AI 文本消息
    final_output = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content and not (getattr(m, "tool_calls", None)):
            final_output = str(m.content)
            break

    if not final_output:
        fallback = llm.invoke(
            messages
            + [
                HumanMessage(
                    content="请停止调用工具，基于以上已获得的分析结果，立即输出结构化 EDA 报告。"
                )
            ]
        )
        _log_usage(task_id, "preprocessing_fallback", fallback)
        final_output = str(fallback.content)

    # 持久化 EDA 图表，并把报告里的临时 run_id URL 改写为持久链接
    _persisted = _persist_task_files(task_id, image_urls=all_images)
    for _old, _new in (_persisted.get("url_map") or {}).items():
        final_output = final_output.replace(_old, _new)

    _pub_event(
        task_id,
        "node_end",
        "data_preprocessing_agent",
        {
            "step": idx + 1,
            "output_length": len(final_output),
            "images_count": len(all_images),
            "summary": final_output[:800],
            "title": "数据预处理",
            "desc": f"EDA 报告 {len(final_output)} 字"
            + (f"，图表 {len(all_images)} 张" if all_images else ""),
        },
    )

    if state["mode"] == "execute":
        _save_working_memory(
            task_id, "preprocessing", final_output, extra={"images_count": len(all_images)}
        )

    return {
        "preprocessed_data": final_output,
        "current_step_index": idx,
        "messages": [
            SystemMessage(
                content=f"[预处理Agent] 第{idx + 1}步完成，"
                f"图表 {len(all_images)} 张，"
                f"输出 {len(final_output)} 字"
            )
        ],
    }


# ============================================================
# 节点: 结果导出
# ============================================================
