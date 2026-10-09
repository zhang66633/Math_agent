"""Solving agent node - code implementation, sandbox execution, ReAct self-correction.

Split from core/nodes.py: nodes.py keeps only orchestration nodes
(classify/retrieve/plan/format_response) plus re-exports.
"""

from __future__ import annotations

import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.config import get_settings
from app.core.state import AgentState
from app.tools.interaction_tools import RunCodeTool
from app.tools.kb_tools import create_kb_tools
from app.tools.math_tools import create_math_tools
from app.tools.web_search_tools import create_web_search_tools

from ..llm.factory import get_llm
from ..node_helpers import (
    _check_cancelled,
    _collect_file_urls,
    _collect_image_urls,
    _log_usage,
    _next_step,
    _persist_task_files,
    _pub_event,
    _save_working_memory,
    get_cancel_event,
    invoke_streaming_with_retry,
    invoke_with_retry,
    parse_code_result,
    tool_call_id,
    tool_timeout,
)
from ..prompts.solving import (
    SOLVING_TEACH_SYSTEM_PROMPT,
    SOLVING_TEACH_USER_TEMPLATE,
    SOLVING_TOOL_SYSTEM_PROMPT,
    SOLVING_TOOL_USER_TEMPLATE,
)


def solving_agent_node(state: AgentState) -> dict:
    """求解计算 Agent。

    - teach 模式：引导式教学（不执行代码）。
    - execute 模式：多轮 tool loop —— 通过 bind_tools 动态调用
      run_code / sympy / 优化 / 知识库 / 搜索，形成"求解→检验→灵敏度"闭环，
      产出证据驱动的结构化求解报告。
    """
    idx = _next_step(state)
    task_id = state["session_id"]
    _check_cancelled(task_id)
    _pub_event(task_id, "node_start", "solving_agent", {"step": idx + 1})
    llm = get_llm("solving", state.get("api_key_config"))

    model_text = state.get("model_output") or "无模型"

    # ── teach 模式：保持原有引导式输出（流式）──
    if state["mode"] == "teach":
        system_prompt = SOLVING_TEACH_SYSTEM_PROMPT.format(model_info=model_text[:3000])
        user_prompt = SOLVING_TEACH_USER_TEMPLATE.format(
            problem=state["problem_raw"],
            model=model_text[:3000],
        )
        final_output, usage = invoke_streaming_with_retry(
            llm,
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ],
            task_id=task_id,
            node="solving_agent",
        )
        _log_usage(task_id, "solving_teach", usage)
        _pub_event(
            task_id,
            "node_end",
            "solving_agent",
            {
                "step": idx + 1,
                "output_length": len(final_output),
                "images_count": 0,
                "summary": final_output[:800],
                "title": "求解计算",
                "desc": f"输出 {len(final_output)} 字（教学模式）",
            },
        )
        return {
            "solving_output": final_output,
            "current_step_index": idx,
            # 消费回退标志（求解回退目标）：防止路由再次回到 solving 自循环
            "rollback_target": None,
            "messages": [SystemMessage(content=f"[求解Agent] 第{idx + 1}步完成（教学模式）")],
        }

    # ── execute 模式：多轮 tool loop ──
    # 注入数据文件目录到 RunCodeTool
    run_code_tool = RunCodeTool()
    run_code_tool.data_files_dir = state.get("data_files_dir", "")

    tools = [run_code_tool] + create_math_tools() + create_kb_tools() + create_web_search_tools()
    tool_map = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    # 构建数据文件上下文（注入系统 prompt 的 {data_files_section} 占位符；
    # 无文件时也要明确告知，防止模型臆造不存在的文件名——审查 P0-1 修复）
    data_files_list = state.get("data_files") or []
    if data_files_list:
        _lines = ["题目数据文件已挂载到沙箱工作目录，**直接用文件名读取，不要传 file_ids**："]
        for df in data_files_list:
            _lines.append(
                f"- `{df.get('filename', '?')}`: "
                f"{df.get('rows', '?')}行, "
                f"列: {', '.join(df.get('columns', []))}"
            )
        _lines.append(
            "用 pd.read_csv / pd.read_excel / pd.read_parquet 按扩展名选择读取方式；"
            "大文件优先采样或聚合后再分析。"
        )
        data_files_section = "\n".join(_lines)
    else:
        data_files_section = (
            "本题**没有预挂载的数据文件**。如需数据支撑，请依据题目描述构造合理的模拟/示例数据，"
            "并在报告中明确说明数据来源与构造假设；禁止尝试读取任何未列出的文件。"
        )

    system_prompt = SOLVING_TOOL_SYSTEM_PROMPT.format(
        model_info=model_text,
        data_files_section=data_files_section,
        # 时间预算如实告知（审查 P0-3）：模型按真实预算规划拆分，
        # 而不是撞了超时才盲目重试同样的大计算
        time_budget_section=(
            f"- 单次 run_code 执行预算约 {get_settings().sandbox_timeout} 秒，"
            "超时会被强制终止（只能拿到终止前的部分输出）。\n"
            "- 预计超过预算的计算必须拆分：先小规模/小迭代跑通验证正确性，"
            "再分步放大规模；严禁单次调用塞入全量重计算。"
        ),
    )
    # EDA 结论注入求解侧（审查 P1：preprocessed_data 曾是悬空字段，EDA 结论被丢弃）
    _eda = (state.get("preprocessed_data") or "").strip()
    eda_block = f"\n## 数据预处理结论（EDA）\n{_eda[:3000]}\n" if _eda else ""
    user_prompt = SOLVING_TOOL_USER_TEMPLATE.format(
        problem=state["problem_raw"],
        model=model_text,
        eda_block=eda_block,
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    all_images: list[str] = []
    all_xlsx: list[str] = []
    all_csv: list[str] = []
    all_html: list[str] = []
    max_rounds = 10  # 工具调用轮数上限（每轮可并发多个工具）

    # 工具结果截断目录（借鉴 cc-haha maxResultSizeChars）
    # 注意：不使用局部 from ..config import get_settings —— 会遮蔽模块级导入，
    # 令上文 time_budget_section f-string 里的 get_settings() 触发 F823（未赋值即引用）
    _settings = get_settings()
    _persist_dir = _settings.project_root / "data" / "task_files" / task_id
    _persist_dir.mkdir(parents=True, exist_ok=True)

    MAX_TOOL_RESULT_CHARS = 12000

    def _truncate_tool_result(result_text: str, tool_name: str) -> str:
        """截断超长工具结果，完整内容写入磁盘（借鉴 cc-haha）。

        错误段保护：interaction_tools 把「错误：…」拼在结果末尾，
        头部截断会把错误整体切掉——LLM 看到失败却看不到原因（审查 P1）。
        截断后无条件回追错误段。
        """
        if len(result_text) <= MAX_TOOL_RESULT_CHARS:
            return result_text
        import uuid as _uuid

        persist_path = _persist_dir / f"_tool_{tool_name}_{_uuid.uuid4().hex[:8]}.txt"
        try:
            persist_path.write_text(result_text, encoding="utf-8")
        except Exception:
            pass
        kept = result_text[:MAX_TOOL_RESULT_CHARS]
        note = (
            f"\n\n…（结果已截断，共 {len(result_text)} 字符。完整结果已保存至 {persist_path}）"
        )
        # 回追错误段（截断点之后的所有以「错误」开头的行及其后续缩进行）
        err_lines: list[str] = []
        for ln in result_text[MAX_TOOL_RESULT_CHARS:].splitlines():
            if ln.lstrip().startswith(("错误", "error", "Error", "ERROR")) or (
                err_lines and (ln.startswith((" ", "\t")) )
            ):
                err_lines.append(ln)
        if err_lines:
            kept = kept.rstrip() + "\n\n" + "\n".join(err_lines[-30:])
        return kept + note

    for _ in range(max_rounds):
        _check_cancelled(task_id)
        response = invoke_with_retry(llm_with_tools, messages, task_id=task_id, node="solving_tool")
        _log_usage(task_id, "solving_tool", response)
        messages.append(response)
        # 每轮 LLM 解说文本推给前端（与流式节点的 node_delta 同通道，逐轮累积）
        round_text = getattr(response, "content", "") or ""
        if round_text:
            _pub_event(task_id, "node_delta", "solving_agent", {"delta": str(round_text)})

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break  # LLM 停止调用工具 → 最后一条即结构化求解报告

        # ── 协议 v2.1：先发 tool_call（running，带 tool_call_id），
        #    执行完再发 tool_result（同一 id 回声）——前端同一卡片两段更新，内联成组 ──
        for tc in tool_calls:
            _pub_event(
                task_id,
                "tool_call",
                "solving_agent",
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

        # ── 执行：run_code 串行（沙箱资源独占，注入取消事件）；
        #    其余工具线程池并行 + 每工具超时（与 chat 通道同规则）──
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

        # run_code 串行执行：任务取消 → 沙箱进程树被中断（事件级取消）
        run_code_tool.cancel_event = get_cancel_event(task_id)
        for tc in tool_calls:
            if tc.get("name") != "run_code":
                continue
            tc_id = tool_call_id(tc, "run_code")
            _pub_event(task_id, "code_exec", "solving_agent", {"status": "running", "id": tc_id})
            text, meta = _run_one(tc)
            results[tc_id] = (text, meta)
            code_data = parse_code_result(text)
            _pub_event(
                task_id,
                "code_exec",
                "solving_agent",
                {
                    "status": "done",
                    "id": tc_id,
                    **code_data,
                    "ok": meta["ok"],
                    "duration_ms": meta["duration_ms"],
                },
            )

        # 其余工具并行（每工具独立超时；超时仅放弃等待，不杀线程——与 chat 一致）
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

        # ── 结果事件回灌（按 LLM 原始顺序，id 回声）──
        for tc in tool_calls:
            tc_id = tool_call_id(tc, tc.get("name"))
            tool_name = tc.get("name")
            text, meta = results[tc_id]

            # run_code 的图/文件 URL 在结果文本末尾,截断会丢 → 先留存原行
            url_lines: list[str] = []
            if tool_name == "run_code":
                url_lines = [
                    ln for ln in text.splitlines()
                    if "/api/images/" in ln or "/api/task_files/" in ln
                ]

            # 截断超长工具结果（借鉴 cc-haha maxResultSizeChars）
            text = _truncate_tool_result(text, tool_name)

            # 截断后回补 URL 行: 求解 LLM 与事件里图链接必须完整,论文才有图
            if url_lines:
                text = f"{text.rstrip()}\n\n" + "\n".join(url_lines)

            # 收集 run_code 产出的图表和文件 URL
            if tool_name == "run_code":
                all_images.extend(_collect_image_urls(text))
                all_xlsx.extend(_collect_file_urls(text, "xlsx"))
                all_csv.extend(_collect_file_urls(text, "csv"))
                all_html.extend(_collect_file_urls(text, "html"))

            _pub_event(
                task_id,
                "tool_result",
                "solving_agent",
                {
                    "tool_call_id": tc_id,
                    "tool_name": tool_name,
                    "preview": text[:1500],
                    "ok": meta["ok"],
                    "duration_ms": meta["duration_ms"],
                    "images": _collect_image_urls(text),
                    "xlsx_files": _collect_file_urls(text, "xlsx"),
                    "csv_files": _collect_file_urls(text, "csv"),
                    "html_files": _collect_file_urls(text, "html"),
                    **({"error": meta["error"]} if meta.get("error") else {}),
                },
            )

            messages.append(
                ToolMessage(
                    content=text,
                    tool_call_id=tc_id,
                )
            )

    # 最终求解报告 = 最后一条 AI 文本消息
    final_output = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content and not (getattr(m, "tool_calls", None)):
            final_output = str(m.content)
            break

    if not final_output:
        # 兜底：轮数耗尽仍在调工具，强制让 LLM 基于已有结果总结
        fallback = llm.invoke(
            messages
            + [
                HumanMessage(
                    content="请停止调用工具，基于以上已获得的全部求解结果，立即输出结构化求解报告。"
                )
            ]
        )
        _log_usage(task_id, "solving_fallback", fallback)
        final_output = str(fallback.content)

    # 图表和文件持久化到任务文件区（临时目录可能被系统清理）
    # 先按 URL 去重（审查 B5）：多轮重试/多子问题常引用同一 run 的同一张图，
    # 不去重会虚报 images_count，也会诱导下游写作阶段多处引用同一图
    all_images = list(dict.fromkeys(all_images))
    all_xlsx = list(dict.fromkeys(all_xlsx))
    all_csv = list(dict.fromkeys(all_csv))
    all_html = list(dict.fromkeys(all_html))
    persisted = _persist_task_files(
        task_id,
        image_urls=all_images,
        xlsx_urls=all_xlsx,
        csv_urls=all_csv,
        html_urls=all_html,
    )
    # 临时 run_id URL → 持久 task_id URL 整体改写：
    # 论文/写作素材只保留永久链接，否则 24h 清理后论文图必裂（审查 P1）
    url_map: dict = persisted.get("url_map") or {}
    if url_map and final_output:
        for _old, _new in url_map.items():
            final_output = final_output.replace(_old, _new)

    _pub_event(
        task_id,
        "node_end",
        "solving_agent",
        {
            "step": idx + 1,
            "output_length": len(final_output),
            "images_count": len(all_images),
            "xlsx_count": len(all_xlsx),
            "csv_count": len(all_csv),
            "summary": final_output[:800],
            "title": "求解计算",
            "desc": f"输出 {len(final_output)} 字"
            + (f"，图表 {len(all_images)} 张" if all_images else ""),
        },
    )

    if state["mode"] == "execute":
        _save_working_memory(
            task_id, "solving", final_output, extra={"images_count": len(all_images)}
        )

    return {
        "solving_output": final_output,
        "current_step_index": idx,
        # 消费回退标志（求解回退目标）：防止路由再次回到 solving 自循环
        "rollback_target": None,
        "messages": [
            SystemMessage(
                content=f"[求解Agent] 第{idx + 1}步完成，"
                f"图表 {len(all_images)} 张，"
                f"输出 {len(final_output)} 字"
            )
        ],
    }


