import { useAuthStore } from "@/stores/auth";
import { useChatSessionStore } from "@/stores/chatSession";
import type { Message, ToolMessage } from "@/types/response";
import { TaskWebSocket } from "@/utils/websocket";
import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";

// ── WS 进度事件类型（与后端 ProgressEvent envelope 对齐，替代 Record<string, any>）──
interface WsEventData {
  plan?: string[];
  step_count?: number;
  reasons?: Record<string, string>;
  stage?: string;
  title?: string;
  summary?: string;
  desc?: string;
  output_length?: number;
  images_count?: number;
  stdout?: string;
  passed?: boolean;
  rollback_target?: string;
  skipped?: boolean;
  delta?: string;
  reset?: boolean;
  tool_name?: string;
  tool_call_id?: string;
  id?: string;
  input?: Record<string, unknown>;
  output?: unknown[];
  status?: string;
  preview?: string;
  ok?: boolean;
  duration_ms?: number;
  error?: string;
  images?: string[];
  xlsx_files?: string[];
  csv_files?: string[];
  html_files?: string[];
  final_response_preview?: string;
  final_response_length?: number;
  message?: string;
}

interface WsEvent {
  event: string;
  node?: string;
  task_id?: string;
  timestamp?: string;
  id?: string;
  /** 事件序号（协议 v2.2）：每任务单调递增，幂等去重与断线增量补拉的依据 */
  seq?: number;
  data?: WsEventData;
}

// 流式节点白名单：这些节点的 LLM 输出逐字渲染（node_delta 事件驱动），
// 与 chat 模式体验一致；其余节点（分类/检索/计划/导出/写作）保持摘要式。
const STREAMING_NODES = new Set([
  "analysis_agent",
  "modeling_agent",
  "solving_agent",
  "verification_agent",
  "data_preprocessing_agent",
]);

function genId() {
  return `tmsg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export const useTaskStore = defineStore("task", () => {
  // 每个 task 的进度/结果消息（system 进度 + agent 最终答案）
  const messagesByTask = ref<Record<string, Message[]>>({});
  const currentTaskId = ref<string | null>(null);
  // solution 任务的进度消息由 solution/index.vue 通过 watch 同步到 chatSession，
  // 保证切页/刷新后不丢失；taskStore 仅作 WS 连接管理 + 即时进度缓存。
  let ws: TaskWebSocket | null = null;
  const wsStatus = ref<
    "connecting" | "connected" | "disconnected" | "reconnecting"
  >("disconnected");
  const isRunning = ref(false);
  const completed = ref(false);
  const currentStep = ref<string>("");
  // 写作阶段并行生成状态（node_progress 事件驱动：outline → section×N → abstract → red_team → revise）
  const writingStage = ref<string | null>(null);
  const sectionsDone = ref(0);
  // 动态执行计划（plan 事件；波次 2 用真实计划渲染时间线，替换写死步骤）
  const planSteps = ref<string[]>([]);
  // 计划步骤 → 理由（v2.2：planner 输出 [{step, reason}]，时间线按真实理由展示"方案思考"）
  const planReasons = ref<Record<string, string>>({});
  // 每任务已处理的最大事件序号（协议 v2.2）：WS 实时事件 vs REST 回放竞态
  // 双apply 的幂等依据；重连后按 after=lastSeq 增量补拉断线期间丢失的事件
  const lastSeqByTask: Record<string, number> = {};
  // 节点状态（node_start/node_end 驱动）：node 名 → active/done/skipped + 描述
  const nodeStates = ref<
    Record<string, { status: "active" | "done" | "skipped"; detail?: string }>
  >({});
  // 验证回退信息（verification FAIL 时记录，时间线显示"回退重试"）
  const rollbackInfo = ref<{ target: string; count: number } | null>(null);
  // 流式节点当前消息：node 名 → agent 消息 id（node_start 创建 → node_delta 累积 → node_end 收尾）
  const streamingNodeMsg = ref<Record<string, string>>({});
  // 工具消息归属：toolMsgId → 宿主 agent 消息 id（工具卡片内联进对应 agent 回复）
  const toolHostMap = ref<Record<string, string>>({});

  // 工具内联复用 chat 模式的附件/片段流机制（同一 store，Bubble 渲染层零改动）
  const chatSession = useChatSessionStore();

  const messages = computed<Message[]>(() => {
    if (!currentTaskId.value) return [];
    return messagesByTask.value[currentTaskId.value] ?? [];
  });

  function ensureTaskBucket(taskId: string) {
    if (!messagesByTask.value[taskId]) {
      messagesByTask.value[taskId] = [];
    }
  }

  function appendMessage(taskId: string, message: Message) {
    ensureTaskBucket(taskId);
    const bucket = messagesByTask.value[taskId];
    // 幂等：同 id 已存在则合并更新，而不是再追加（确定性 id + 回放/重连
    // 会重复触发同一事件，旧实现无限追加 → 重复气泡；审查 B2）
    const idx = bucket.findIndex((m) => m.id === message.id);
    if (idx >= 0) {
      bucket[idx] = { ...bucket[idx], ...message } as Message;
      messagesByTask.value = { ...messagesByTask.value, [taskId]: [...bucket] };
      return;
    }
    messagesByTask.value[taskId] = [...bucket, message];
  }

  /** 更新 task 内已存在的消息（同 id 覆盖，供工具结果/代码执行回填） */
  function updateMessage(
    taskId: string,
    messageId: string,
    patch: Partial<Message>,
  ) {
    const bucket = messagesByTask.value[taskId];
    if (!bucket) return;
    const idx = bucket.findIndex((m) => m.id === messageId);
    if (idx === -1) return;
    // 联合类型展开会退化为并集,显式断言回 Message
    const updated = { ...bucket[idx], ...patch } as Message;
    bucket[idx] = updated;
    messagesByTask.value = { ...messagesByTask.value, [taskId]: [...bucket] };
  }

  /** 找最近的 tool 消息：优先 tool_call_id 精确匹配，退化最近同名未完成 */
  function findToolMessage(
    taskId: string,
    toolCallId?: string,
    toolName?: string,
  ) {
    const bucket = messagesByTask.value[taskId];
    if (!bucket) return null;
    return findToolInList(bucket, toolCallId, toolName);
  }

  /** 工具消息 → 宿主 agent 消息 id（内联场景）。 */
  function findToolHost(toolCallId?: string): string | null {
    if (!toolCallId) return null;
    return toolHostMap.value[toolCallId] ?? null;
  }

  /** 在工具消息列表中按 tool_call_id 精确/退化匹配。 */
  function findToolInList(
    list: Message[],
    toolCallId?: string,
    toolName?: string,
  ): ToolMessage | null {
    if (toolCallId) {
      const hit = [...list]
        .reverse()
        .find(
          (m): m is ToolMessage =>
            m.msg_type === "tool" && m.tool_call_id === toolCallId,
        );
      if (hit) return hit;
    }
    if (toolName) {
      return (
        [...list]
          .reverse()
          .find(
            (m): m is ToolMessage =>
              m.msg_type === "tool" &&
              m.tool_name === toolName &&
              (m.status === "running" || !m.output),
          ) ?? null
      );
    }
    return null;
  }

  function setCurrentTask(taskId: string) {
    currentTaskId.value = taskId;
  }

  function now() {
    return new Date().toISOString();
  }

  /** 事件 → 时间线状态更新（plan / node_start / node_end / task_end）。
   * WS 实时事件与 GET /tasks/{id}/events 回放共用同一实现。 */
  function applyEventState(data: WsEvent) {
    const event = data?.event;
    const node = data?.node;
    if (event === "plan") {
      const plan: string[] = Array.isArray(data.data?.plan)
        ? data.data.plan
        : [];
      if (plan.length) planSteps.value = plan;
      planReasons.value = (data.data?.reasons as Record<string, string>) ?? {};
      // plan 事件即"计划制定"步骤完成（该节点不发 node_end）
      nodeStates.value = {
        ...nodeStates.value,
        plan_execution: { status: "done" },
      };
    } else if (event === "node_start") {
      if (node) {
        nodeStates.value = {
          ...nodeStates.value,
          [node]: { status: "active" },
        };
      }
    } else if (event === "node_end") {
      if (node) {
        const d = data.data ?? {};
        nodeStates.value = {
          ...nodeStates.value,
          [node]: {
            status: d.skipped ? "skipped" : "done",
            detail: d.desc ?? "",
          },
        };
        // 验证 FAIL → 记录回退（时间线显示"回退重试"）；PASS → 清除
        if (node === "verification_agent") {
          if (d.passed === false) {
            rollbackInfo.value = {
              target: d.rollback_target ?? "modeling",
              count: (rollbackInfo.value?.count ?? 0) + 1,
            };
          } else if (d.passed === true) {
            rollbackInfo.value = null;
          }
        }
      }
    } else if (event === "task_end") {
      // 任务结束：active 节点兜底置为 done（断连/丢事件时不残留"进行中"）
      const cleaned: Record<
        string,
        { status: "active" | "done" | "skipped"; detail?: string }
      > = {};
      for (const [k, v] of Object.entries(nodeStates.value)) {
        cleaned[k] = v.status === "active" ? { ...v, status: "done" } : v;
      }
      nodeStates.value = cleaned;
    }
  }

  /** 拉取任务持久化事件流，重放时间线状态（刷新/切页恢复动态轨迹）。 */
  async function fetchTaskEvents(taskId: string) {
    try {
      const { getTaskEvents } = await import("@/apis/commonApi");
      const res = await getTaskEvents(taskId);
      const data = res.data?.data ?? res.data;
      const events: WsEvent[] = data?.events ?? [];
      planSteps.value = [];
      planReasons.value = {};
      nodeStates.value = {};
      rollbackInfo.value = null;
      let sawTaskEnd = false;
      for (const ev of events) {
        applyEventState(ev);
        if (ev.event === "task_end") sawTaskEnd = true;
      }
      // 回放后置任务态：有 task_end → 已完成；否则仍在跑
      if (sawTaskEnd) {
        isRunning.value = false;
        completed.value = true;
        currentStep.value = "已完成";
      } else {
        isRunning.value = true;
        completed.value = false;
      }
    } catch {
      /* 回放失败不阻塞（退化为默认计划时间线） */
    }
  }

  function handleProgressEvent(taskId: string, data: WsEvent) {
    const event = data?.event;

    // ── 幂等去重（协议 v2.2）：带 seq 的事件只应用一次 ──
    // 连接后 REST 回放与实时 WS 存在重叠窗口，逐事件重放会让 node_delta
    // 文本翻倍、tool_call 重复建卡（图表重复出现；审查 B2）。
    // 同一个事件（同 seq）只更新 lastSeq 之后的首次应用。
    const seq = data?.seq;
    if (typeof seq === "number") {
      if (seq <= (lastSeqByTask[taskId] ?? 0)) return;
      lastSeqByTask[taskId] = seq;
    }

    // 动态时间线状态（plan/node_start/node_end/task_end）——与消息卡片无关，
    // 抽成 applyEventState 供 WS 实时事件与 events 回放共用
    applyEventState(data);

    // 动态执行计划（协议 v2.1：前端按真实计划渲染时间线）
    if (event === "plan") {
      return;
    }

    // 写作阶段细粒度进度（并行生成章节提示）
    if (event === "node_progress") {
      const stage: string | undefined = data.data?.stage;
      if (stage) writingStage.value = stage;
      if (stage === "outline") sectionsDone.value = 0;
      if (stage === "section") sectionsDone.value += 1;
      return;
    }

    // 流式节点开始：创建 agent 消息占位（node_delta 逐字累积，体验对齐 chat 模式）。
    // id 用确定性 node-{node}：回放/重连重复触发同一 node_start 时幂等合并，
    // 而不是再建占位；节点重跑（回退到 modeling/solving）时重置内容防旧流叠加。
    if (event === "node_start") {
      const node = data?.node;
      if (node && STREAMING_NODES.has(node)) {
        const msgId = `node-${node}`;
        const existing = messagesByTask.value[taskId]?.find(
          (m) => m.id === msgId,
        );
        if (existing) {
          updateMessage(taskId, msgId, {
            content: "",
            streaming: true,
          } as Partial<Message>);
        } else {
          appendMessage(taskId, {
            id: msgId,
            msg_type: "agent",
            content: "",
            streaming: true,
            created_at: now(),
          } as Message);
        }
        streamingNodeMsg.value = {
          ...streamingNodeMsg.value,
          [node]: msgId,
        };
      }
      return;
    }

    // 流式文本增量：累积到对应节点消息（dsh 式逐字渲染）
    if (event === "node_delta") {
      const node = data?.node;
      if (!node) return;
      const msgId = streamingNodeMsg.value[node];
      if (!msgId) return;
      // 流式重试 reset：清空已收到的增量重新累积（避免失败流与重试流重复）
      if (data.data?.reset) {
        updateMessage(taskId, msgId, { content: "" } as Partial<Message>);
        return;
      }
      const delta: string = data.data?.delta ?? "";
      if (!delta) return;
      const bucket = messagesByTask.value[taskId];
      const cur = bucket?.find((m) => m.id === msgId);
      const acc = ((cur?.content as string) ?? "") + delta;
      updateMessage(taskId, msgId, { content: acc } as Partial<Message>);
      return;
    }

    // 工具调用：挂到当前流式节点消息（内联进 agent 回复，与 chat 模式一致）
    if (event === "tool_call") {
      const hostId = Object.values(streamingNodeMsg.value).pop() ?? null;
      const toolCallId = data.data?.tool_call_id;
      // 确定性 id：tool-{tool_call_id} —— tool_result 按 tool_call_id 回填；
      // 回放/重连重复触发同一 tool_call 时幂等合并，不重复建卡（图表重复 B2）
      const toolMsgId = `tool-${toolCallId ?? genId()}`;
      const toolMsg: Message = {
        id: toolMsgId,
        msg_type: "tool",
        tool_name: data.data?.tool_name ?? "run_code",
        input: data.data?.input ?? null,
        output: null,
        status: "running",
        tool_call_id: toolCallId,
        created_at: now(),
      };
      if (hostId) {
        // 内联：挂到宿主 agent 消息的附件/片段流（Bubble 渲染层复用 chat 机制）
        const existing = chatSession
          .getToolAttachments(hostId)
          .find((m) => m.id === toolMsgId);
        if (!existing) {
          chatSession.attachTool(hostId, toolMsg);
          chatSession.appendSegment(hostId, {
            kind: "tool",
            toolId: toolMsgId,
          });
        }
        // 键必须与读取端（findToolHost 按 tool_call_id 查）一致：
        // 优先后端 tool_call_id，缺失时回退前端消息 id
        const toolKey = toolCallId ?? toolMsgId;
        toolHostMap.value = { ...toolHostMap.value, [toolKey]: hostId };
      } else {
        appendMessage(taskId, toolMsg);
      }
      return;
    }

    // 工具结果（协议 v2.1：按 id 回填同一卡片，修复"调用在后、输出在前"的割裂）
    if (event === "tool_result") {
      const d = data.data ?? {};
      // 内联路径：工具卡片挂在宿主 agent 消息的附件里（chatSession 机制）
      const hostId = findToolHost(d.tool_call_id);
      if (hostId) {
        const tools = chatSession.getToolAttachments(hostId);
        const target = findToolInList(tools, d.tool_call_id, d.tool_name);
        if (target) {
          target.output = [
            {
              name: d.tool_name,
              preview: d.preview ?? "",
              images: d.images ?? [],
              xlsx_files: d.xlsx_files ?? [],
              csv_files: d.csv_files ?? [],
              html_files: d.html_files ?? [],
            },
          ];
          target.status = d.ok === false ? "error" : "success";
          target.error = d.ok === false ? d.error : undefined;
          target.duration_ms = d.duration_ms;
        }
        return;
      }
      // 独立消息路径（旧事件/无宿主时兜底）
      const target = findToolMessage(taskId, d.tool_call_id, d.tool_name);
      if (!target) return;
      updateMessage(taskId, target.id, {
        output: [
          {
            name: d.tool_name,
            preview: d.preview ?? "",
            images: d.images ?? [],
            xlsx_files: d.xlsx_files ?? [],
            csv_files: d.csv_files ?? [],
            html_files: d.html_files ?? [],
          },
        ],
        status: d.ok === false ? "error" : "success",
        error: d.ok === false ? d.error : undefined,
        duration_ms: d.duration_ms,
      } as Partial<Message>);
      return;
    }

    // 代码执行态（run_code 的 running/done 帧，与 chat 通道协议一致）
    if (event === "code_exec") {
      const d = data.data ?? {};
      const hostId = findToolHost(d.id);
      let target: Message | null = null;
      if (hostId) {
        target =
          findToolInList(
            chatSession.getToolAttachments(hostId),
            d.id,
            "run_code",
          ) ?? null;
      }
      if (!target) {
        target = findToolMessage(taskId, d.id, "run_code");
      }
      if (!target) return;
      if (d.status === "running") {
        target.output = [{ name: "run_code", preview: "代码执行中…" }];
        target.status = "running";
      } else if (d.status === "done") {
        const parts = [];
        if (d.stdout) parts.push(`输出:\n${d.stdout}`);
        if (d.images?.length) parts.push(`图表: ${d.images.length} 张`);
        target.output = [
          {
            name: "run_code",
            preview: parts.join("\n") || "执行完成",
            images: d.images ?? [],
          },
        ];
        target.status = d.ok === false ? "error" : "success";
        target.error = d.ok === false ? d.error : undefined;
        target.duration_ms = d.duration_ms;
      }
      return;
    }

    // 节点完成：追加一条 agent 消息，思考内容放入 thinking 字段
    // 这样 BubbleAgent + ThinkingBlock 可以渲染可折叠的思考过程
    if (event === "node_end") {
      const node = data?.node;
      if (!node) return;
      // 流式节点收尾：内容已由 node_delta 逐字累积，只结束 streaming 态。
      // 求解/预处理有工具循环：循环文本一次性补推、最终报告用 summary 兜底
      const streamMsgId = streamingNodeMsg.value[node];
      if (streamMsgId) {
        const bucket = messagesByTask.value[taskId];
        const cur = bucket?.find((m) => m.id === streamMsgId);
        const curContent = (cur?.content as string) ?? "";
        if (!curContent) {
          const summary: string = (data.data?.summary ?? "").trim();
          updateMessage(taskId, streamMsgId, {
            content: summary || "已完成",
            streaming: false,
          } as Partial<Message>);
        } else {
          updateMessage(taskId, streamMsgId, {
            streaming: false,
          } as Partial<Message>);
        }
        const rest = { ...streamingNodeMsg.value };
        delete rest[node];
        streamingNodeMsg.value = rest;
        currentStep.value = data.data?.stage ?? currentStep.value;
        return;
      }

      const stage = data.data?.stage ?? "";
      const title = data.data?.title ?? stage;
      const summary: string = (data.data?.summary ?? "").trim();
      const outputLength = data.data?.output_length ?? 0;
      const passed = data.data?.passed;
      const imagesCount = data.data?.images_count ?? 0;

      // 构建给用户看的摘要
      let content = "";
      if (passed !== undefined) {
        content = passed ? "验证通过" : "验证不通过";
      } else if (imagesCount > 0) {
        content = `求解完成，输出 ${outputLength} 字，图表 ${imagesCount} 张`;
      } else if (outputLength > 0) {
        content = `输出 ${outputLength} 字`;
      }
      // 兜底：部分节点（如跳过分支）无输出字段 → 完成提示，避免空内容三点假气泡
      if (!content) {
        content = title ? `已完成：${title}` : "已完成";
      }

      appendMessage(taskId, {
        // 确定性 id：nodeend-{node}——回放/重连重复触发同一 node_end 时
        // 合并更新（appendMessage 幂等），而不是再造一条气泡（审查 B1/B2）
        id: data.id ?? `nodeend-${node}`,
        msg_type: "agent",
        content,
        agent_type: undefined,
        // 只有真实摘要才渲染思考块（去掉"X 分析完成"类无信息量占位）
        thinking: summary.length > 0 ? summary : undefined,
        streaming: false,
        created_at: now(),
      } as Message);
      currentStep.value = stage || currentStep.value;
      return;
    }

    // 任务结束：停止运行态，主动拉完整 final_response 渲染
    if (event === "task_end") {
      isRunning.value = false;
      completed.value = true;
      currentStep.value = "已完成";
      const finalPreview: string = data.data?.final_response_preview ?? "";
      if (data.data?.final_response_length) {
        // 先展示轻量预览，再异步 GET 完整内容并替换
        if (finalPreview) {
          appendMessage(taskId, {
            id: `final-${taskId}`,
            msg_type: "agent",
            content:
              finalPreview +
              (data.data.final_response_length > finalPreview.length
                ? "\n\n_（正在加载完整论文…）_"
                : ""),
            streaming: false,
            created_at: now(),
          });
        }
        // 异步拉取完整内容
        fetchFullFinalResponse(taskId).catch((e) => {
          console.error("拉取完整论文失败：", e);
          // 清除占位消息中的"正在加载"提示，避免残留
          const bucket = messagesByTask.value[taskId];
          if (bucket) {
            const idx = bucket.findIndex((m) => m.id === `final-${taskId}`);
            if (idx !== -1) {
              const cleaned = (bucket[idx].content as string).replace(
                /\n\n_（正在加载完整论文…）_$/,
                "\n\n_（完整论文加载失败，以上为预览片段）_",
              );
              bucket[idx] = { ...bucket[idx], content: cleaned };
              messagesByTask.value = {
                ...messagesByTask.value,
                [taskId]: [...bucket],
              };
            }
          }
        });
      } else if (data.data?.message) {
        appendMessage(taskId, {
          id: genId(),
          msg_type: "system",
          type: "error",
          content: `任务失败：${data.data.message}`,
          created_at: now(),
        } as Message);
      }
      return;
    }
  }

  async function fetchFullFinalResponse(taskId: string) {
    const { getTask } = await import("@/apis/commonApi");
    const res = await getTask(taskId);
    const task = res.data?.data ?? res.data;
    const full: string = task?.final_response ?? task?.writing_output ?? "";
    if (!full) return;
    // 替换占位消息
    const bucket = messagesByTask.value[taskId];
    if (!bucket) return;
    const idx = bucket.findIndex((m) => m.id === `final-${taskId}`);
    if (idx === -1) {
      appendMessage(taskId, {
        id: `final-${taskId}`,
        msg_type: "agent",
        content: full,
        streaming: false,
        created_at: now(),
      });
      return;
    }
    bucket[idx] = { ...bucket[idx], content: full };
    messagesByTask.value = { ...messagesByTask.value, [taskId]: [...bucket] };
  }

  function connectWebSocket(taskId: string) {
    // 短路：若已连到同一任务且连接正常，复用避免切页回来时断开/重连把进度搞丢
    if (
      ws &&
      currentTaskId.value === taskId &&
      wsStatus.value === "connected"
    ) {
      return;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
    setCurrentTask(taskId);
    ensureTaskBucket(taskId);
    isRunning.value = true;
    completed.value = false;
    currentStep.value = "";
    // 重建本次连接的事件基准（审查 B2）：重置 bucket 后做全量回放，
    // 否则切换任务/断线重连会对未清空的 bucket 重复叠加旧消息。
    // chatSession 已持久化副本，displayMessages 按 id 去重，此处重建不丢历史。
    messagesByTask.value[taskId] = [];
    delete lastSeqByTask[taskId];
    streamingNodeMsg.value = {};
    toolHostMap.value = {};

    // 访客也连接：后端 /api/ws 已放行无 token 订阅（此前访客被静默跳过，
    // 方案页看不到任何实时过程——实测复现）。有 token 才附加；无 token 裸连。
    const token = localStorage.getItem("mma:token") || "";
    const baseUrl =
      import.meta.env.VITE_WS_URL || `ws://${window.location.host}/api/ws`;
    const wsUrl = token
      ? `${baseUrl}/task/${taskId}?token=${encodeURIComponent(token)}`
      : `${baseUrl}/task/${taskId}`;

    // 事件回放：初始连接从 after=0 全量重建（bucket 已重置）；断线重连
    // 从最后已处理 seq 增量补拉断连期间丢失的事件。handleProgressEvent 内部
    // 按 seq 幂等去重，重复喂同一事件（实时窗口重叠）也不会二次应用。
    const replay = (after: number) => {
      void (async () => {
        try {
          const res = await fetch(
            `/api/tasks/${taskId}/events?after=${after}&limit=500`,
          );
          if (!res.ok) return;
          const data = await res.json();
          for (const ev of data.events ?? []) {
            handleProgressEvent(taskId, ev as WsEvent);
          }
        } catch {
          // 回放失败不阻断实时连接
        }
      })();
    };

    ws = new TaskWebSocket(
      wsUrl,
      (data) => handleProgressEvent(taskId, data as WsEvent),
      (status) => {
        wsStatus.value = status;
      },
      (isReconnect) => {
        if (isReconnect) replay(lastSeqByTask[taskId] ?? 0);
      },
    );
    ws.connect();

    // REST 回放：pub/sub 无回放缓冲，晚订阅会丢连接前已发布的事件——
    // 拉取持久化事件流按序重建，让访客/晚到者也能看到完整过程
    replay(0);
  }

  // 登录后自动恢复当前任务的 WS 连接（无 token 时被跳过的场景）
  const auth = useAuthStore();
  watch(
    () => auth.token,
    (tok) => {
      if (tok && currentTaskId.value && wsStatus.value !== "connected") {
        connectWebSocket(currentTaskId.value);
      }
    },
  );

  function closeWebSocket() {
    ws?.close();
    ws = null;
  }

  return {
    messages,
    wsStatus,
    isRunning,
    completed,
    currentStep,
    writingStage,
    sectionsDone,
    planSteps,
    planReasons,
    nodeStates,
    rollbackInfo,
    currentTaskId,
    connectWebSocket,
    closeWebSocket,
    setCurrentTask,
    appendMessage,
    updateMessage,
    fetchTaskEvents,
  };
});
// ⚠️ 故意不持久化 taskStore：messagesByTask 含 LLM 全文太大、且不能与 isRunning/
//    completed 同步持久化（否则刷新后会出现"显示思考中但无消息"的白屏诡异状态）。
//    路由切页不丢（pinia store 跨路由保留）；刷新页面后用户需重新触发。
