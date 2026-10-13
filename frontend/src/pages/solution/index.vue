<template>
  <div class="flex h-full bg-background">
    <div class="flex-1 min-w-0 relative">
      <button
        class="absolute top-2 right-2 z-10 inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-background/80 backdrop-blur hover:bg-accent transition-colors"
        title="切换执行进度面板"
        @click="rightPanelOpen = !rightPanelOpen"
      >
        <PanelRight class="h-4 w-4" />
      </button>
      <ChatArea
        :messages="displayMessages"
        :is-running="chatSession.getIsRunning('solution')"
        :cancellable="!!currentTaskId"
        :cancelling="cancelling"
        :session-title="chatSession.activeSolutionSession?.title ?? '新方案'"
        :fold-tool-images="true"
        :show-artifacts="false"
        empty-text="开始建模"
        empty-subtext="描述你的问题，我将输出完整建模方案和论文"
        input-placeholder="描述你想解决的建模问题..."
        @send="handleUserSend"
        @cancel="handleCancel"
        @clear="chatSession.clearSession('solution')"
        @new-session="chatSession.newSession('solution')"
        @open-paper="openPaperViewer"
      />
    </div>
    <Transition name="slide-right">
      <div v-if="rightPanelOpen" class="w-80 shrink-0 border-l bg-background p-4 overflow-y-auto" data-tour="solution-timeline">
        <ProgressTimeline
          :steps="agentSteps"
          :running="taskStore.isRunning"
          :completed="taskStore.completed"
          :ws-status="taskStore.wsStatus"
          :skills="taskStore.planSkills"
          :open="true"
          @toggle="rightPanelOpen = !rightPanelOpen"
        />
        <div v-if="currentTaskId" class="mt-3 font-mono text-[10px] text-muted-foreground break-all">
          Task ID: {{ currentTaskId }}
        </div>

        <!-- 交付物面板（dsh 式 deliverables：图表 / 数据文件 / 文档导出统一 dock）
             分组、正文/过程标注与尺寸展示都在组件内，便于单测与复用 -->
        <DeliverablesPanel
          v-if="currentTaskId"
          :files="taskFiles"
          :paper-markdown="paperMarkdown"
          :completed="taskStore.completed"
          @preview="previewImage = $event"
          @refresh="refreshTaskFiles"
          @export="downloadExport"
          @package="downloadPackage"
        />
      </div>
    </Transition>

    <!-- 图表大图预览 -->
    <div
      v-if="previewImage"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 cursor-zoom-out"
      @click="previewImage = null"
    >
      <img :src="previewImage" class="max-h-full max-w-full rounded-md shadow-xl" />
      <button
        class="absolute top-4 right-4 inline-flex h-8 items-center gap-1 rounded-md bg-white/10 px-3 text-xs text-white hover:bg-white/20 transition-colors"
        @click="previewImage = null"
      >
        <X class="h-3.5 w-3.5" /> 关闭
      </button>
    </div>

    <!-- 论文阅读器（全屏浮层） -->
    <PaperViewer
      v-if="showPaperViewer"
      :markdown="paperContent"
      :task-id="currentTaskId ?? undefined"
      @close="closePaperViewer"
    />
  </div>
</template>

<script setup lang="ts">
import type { ChatFileRef } from "@/apis/chatApi";
import {
  cancelTask,
  createTask,
  getTask,
  getTaskFiles,
} from "@/apis/commonApi";
import ChatArea from "@/components/ChatArea.vue";
import ProgressTimeline, {
  type ProgressStep,
} from "@/components/ProgressTimeline.vue";
import PaperViewer from "@/components/paper/PaperViewer.vue";
import DeliverablesPanel, {
  type TaskFile,
} from "@/components/solution/DeliverablesPanel.vue";
import { toast } from "@/composables/useToast";
import type { ChatSession } from "@/stores/chatSession";
import { useChatSessionStore } from "@/stores/chatSession";
import { useTaskStore } from "@/stores/task";
import type { Message } from "@/types/response";
import { PanelRight, X } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

const chatSession = useChatSessionStore();
const taskStore = useTaskStore();

const rightPanelOpen = ref(true);

// solution 页关联的 task_id：原本想放 taskStore（持久化），但 messagesByTask
// 不持久化会导致"刷新后显示 Task ID 但 messages 为空"白屏。
// 改为：task_id 仅在本次 session 内存中持有，刷新后用户重新触发即可；
// 任务进度消息本身已通过 chatSession.solutionSessions 持久化（向下兼容）。
const currentTaskId = ref<string | null>(null);
const cancelling = ref(false);

/** 当前任务归属的会话 id。
 *
 * 为什么不让同步逻辑直接用 `activeSolutionId`：任务跑着的时候用户可能在
 * 侧栏切到另一个方案会话，进度消息会被写进**别人的**会话（跨会话串消息）。
 * 任务一旦创建就锁定归属会话，回放/切换都以它为准。
 */
const taskSessionId = ref<string | null>(null);

// 文件区：任务的附件 + 生成文件（类型与后端 TaskArtifact 对齐）
const taskFiles = ref<TaskFile[]>([]);

async function fetchTaskFiles(taskId: string) {
  try {
    const res = await getTaskFiles(taskId);
    taskFiles.value = res.data?.files ?? [];
  } catch {
    taskFiles.value = [];
  }
}

/** 手动刷新交付物列表（长任务里文件是分阶段落盘的，不想等事件就点一下）。 */
function refreshTaskFiles() {
  if (currentTaskId.value) void fetchTaskFiles(currentTaskId.value);
}

// 任务确定后拉一次文件区；任务完成（求解出图后）再刷新一次
watch(currentTaskId, (id) => {
  taskFiles.value = [];
  if (id) fetchTaskFiles(id);
});
watch(
  () => taskStore.completed,
  (done) => {
    if (done && currentTaskId.value) fetchTaskFiles(currentTaskId.value);
  },
);
// 求解阶段会陆续产出图表，消息数变化时顺带刷新文件区
watch(
  () => taskStore.messages.length,
  () => {
    if (currentTaskId.value && taskStore.isRunning)
      fetchTaskFiles(currentTaskId.value);
  },
);

// ── 动态轨迹时间线（协议 v2.1：plan 事件驱动步骤，node_start/node_end 驱动状态）──
// plan 的 step key → 展示信息
const STEP_META: Record<string, { label: string; description: string }> = {
  classify: { label: "问题分类", description: "识别问题类型与复杂度" },
  retrieve: { label: "知识检索", description: "检索方法/论文/真题" },
  plan: { label: "计划制定", description: "生成动态执行计划" },
  analysis: { label: "问题分析", description: "识别问题类型，理解题意" },
  modeling: { label: "模型构建", description: "选择并建立数学模型" },
  data_preprocessing: {
    label: "数据预处理",
    description: "EDA 探索与数据清洗",
  },
  solving: { label: "求解计算", description: "生成并执行求解代码" },
  verification: { label: "验证分析", description: "检验模型鲁棒性" },
  export_results: { label: "结果导出", description: "打包结构化文件" },
  writing: { label: "论文写作", description: "生成结构化论文" },
};
// 前期固定三步（分类→检索→计划，任何任务都执行）
const PRE_STEPS = ["classify", "retrieve", "plan"];
// 默认计划（plan 事件未到达/回放失败时兜底）
const DEFAULT_PLAN = [
  ...PRE_STEPS,
  "analysis",
  "modeling",
  "data_preprocessing",
  "solving",
  "verification",
  "export_results",
  "writing",
];
// node 名 → 时间线 step key（node_start/node_end 事件的 node 字段映射）
const NODE_TO_STEP: Record<string, string> = {
  classify_problem: "classify",
  retrieve_knowledge: "retrieve",
  plan_execution: "plan",
  analysis_agent: "analysis",
  modeling_agent: "modeling",
  data_preprocessing_agent: "data_preprocessing",
  solving_agent: "solving",
  verification_agent: "verification",
  export_results_agent: "export_results",
  writing_agent: "writing",
  format_response: "writing",
};

// 写作阶段的动态描述：并行生成章节 + 完成计数（node_progress 事件驱动）
const writingDescription = computed(() => {
  if (taskStore.writingStage === "outline")
    return "先写大纲，随后并行生成各章节…";
  if (taskStore.sectionsDone > 0)
    return `并行生成论文章节：已完成 ${taskStore.sectionsDone} 章`;
  if (
    taskStore.writingStage === "abstract" ||
    taskStore.writingStage === "red_team" ||
    taskStore.writingStage === "revise"
  )
    return "正文完成，正在提炼摘要与红队审校";
  return "并行生成论文章节…";
});

const agentSteps = computed<ProgressStep[]>(() => {
  // 动态计划前置固定三步（分类→检索→计划），时间线全程透明
  const plan = taskStore.planSteps.length
    ? [
        ...PRE_STEPS,
        ...taskStore.planSteps.filter((k) => !PRE_STEPS.includes(k)),
      ]
    : DEFAULT_PLAN;
  const states = taskStore.nodeStates;
  const rollback = taskStore.rollbackInfo;

  return plan.map((key, i) => {
    const meta = STEP_META[key] ?? { label: key, description: "" };
    const relatedNodes = Object.entries(NODE_TO_STEP)
      .filter(([, k]) => k === key)
      .map(([n]) => n);

    let status: ProgressStep["status"] = "wait";
    // 回退重跑：目标步骤回到执行态
    if (rollback && rollback.target === key && taskStore.isRunning) {
      status = "active";
    } else if (relatedNodes.some((n) => states[n]?.status === "active")) {
      status = "active";
    } else if (relatedNodes.some((n) => states[n]?.status === "done")) {
      status = "done";
    } else if (
      relatedNodes.length > 0 &&
      relatedNodes.every((n) => states[n]?.status === "skipped")
    ) {
      status = "skipped";
    }

    let description = meta.description;
    // 优先显示 planner 为这步给出的真实理由（方案思考，审查 C1），而非写死描述
    const planReason = taskStore.planReasons[key];
    if (planReason) {
      description =
        planReason.length > 60 ? `${planReason.slice(0, 60)}…` : planReason;
    }
    if (key === "writing" && status === "active") {
      description = writingDescription.value;
    }
    if (key === "data_preprocessing" && status === "skipped") {
      description = "无数据文件，已跳过";
    }
    if (rollback && rollback.target === key && status === "active") {
      description = `验证未通过，第 ${rollback.count} 次回退重试`;
    }

    return { id: `${i}-${key}`, label: meta.label, description, status };
  });
});

const displayMessages = computed<Message[]>(() => {
  const userMsgs = chatSession.activeSolutionMessages;
  const taskMsgs = currentTaskId.value ? taskStore.messages : [];
  // 去重：taskStore 的消息会被 watcher 同步进 chatSession，直接拼接会重复显示。
  // 同 id 消息优先取 taskStore 版本（实时源），确保完整论文替换预览后立即生效。
  const taskMap = new Map(taskMsgs.map((m) => [m.id, m]));
  const seen = new Set<string>();
  const result: Message[] = [];
  for (const m of [...userMsgs, ...taskMsgs]) {
    if (seen.has(m.id)) continue;
    seen.add(m.id);
    result.push(taskMap.get(m.id) ?? m);
  }
  return result;
});

/** 把 taskStore 推送的进度/final 消息同步到**任务归属会话**（持久化）。
 *
 * 用 taskSessionId 而不是 activeSolutionId：任务跑着时用户可能切到别的
 * 方案会话，按 active 写入会把 A 任务的进度塞进 B 会话（跨会话串消息）。
 * 归属缺失（旧数据/刷新前）才退化为当前活动会话。
 */
function syncTaskMsgToSession(msg: Message) {
  const sid = taskSessionId.value ?? chatSession.activeSolutionId;
  if (!sid) return;
  const session = chatSession.solutionSessions.find((s) => s.id === sid);
  const existing = session?.messages.find((m) => m.id === msg.id);
  if (existing) {
    // 已存在则更新内容（关键：fetchFullFinalResponse 会用完整论文替换
    // 800字预览占位消息，若此处跳过，chatSession 将永远停留在旧预览，
    // 导致完整论文不显示、导出 PDF 只有截断的预览）
    //
    // 反向保护：论文消息**不允许被更短的内容覆盖**。事件回放会先推
    // final_response_preview（截断预览），若此时本地已有完整论文，
    // 直接覆盖会让全文退回预览（拉全文失败就永久截断）。
    if (existing.content !== msg.content) {
      const isPaper = typeof msg.id === "string" && msg.id.startsWith("final-");
      const cur = existing.content ?? "";
      const next = msg.content ?? "";
      if (isPaper && next.length < cur.length) return;
      chatSession.updateMessage("solution", sid, msg.id, {
        content: msg.content,
      });
    }
    return;
  }
  chatSession.addMessage("solution", sid, msg);
}

watch(
  () => taskStore.messages,
  (newMsgs) => {
    // 把新推进来的消息同步到 chatSession（仅同步增量）
    for (const m of newMsgs) syncTaskMsgToSession(m);
  },
  { deep: true },
);

function generateId() {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

async function handleUserSend(text: string, files?: ChatFileRef[]) {
  let sessionId = chatSession.activeSolutionId;
  if (!sessionId) {
    sessionId = chatSession.createSession("solution");
  }

  const userMsg: Message = {
    id: generateId(),
    msg_type: "user",
    content: text,
    // 附件随用户消息持久化，气泡内显示文件 chip
    ...(files && files.length > 0
      ? {
          files: files.map((f) => ({
            file_id: f.file_id,
            filename: f.filename,
          })),
        }
      : {}),
    created_at: new Date().toISOString(),
  };
  chatSession.addMessage("solution", sessionId, userMsg);

  // 如果已有任务在跑，先拒绝发送
  if (chatSession.runningMode !== null) {
    chatSession.addMessage("solution", sessionId, {
      id: generateId(),
      msg_type: "system",
      type: "error",
      content: "当前已有任务在执行，请先等待或停止。",
      created_at: new Date().toISOString(),
    } as Message);
    return;
  }

  chatSession.setRunning("solution");

  try {
    const res = await createTask({ problem: text, mode: "execute", files });
    const taskId = res.data?.task_id ?? res.data?.data?.task_id;
    if (!taskId) throw new Error("未返回 task_id");
    currentTaskId.value = taskId;
    // 锁定任务归属会话：此后进度消息只写进这个会话（用户切走也不串）
    taskSessionId.value = sessionId;
    // 写入 session 持久化（刷新恢复依赖它：onMounted 读 session.taskId 回放）
    const sess = chatSession.activeSolutionSession;
    if (sess) sess.taskId = taskId;
    // 连接 WS 实时接收进度与最终答案；task_end 事件会清空 runningMode
    taskStore.connectWebSocket(taskId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    chatSession.addMessage("solution", sessionId, {
      id: generateId(),
      msg_type: "system",
      type: "error",
      content: `创建任务失败：${msg ?? "后端不可达，请确认已启动 (uvicorn app.main:app --port 8002)"}`,
      created_at: new Date().toISOString(),
    } as Message);
    chatSession.setRunning(null);
    currentTaskId.value = null;
  }
}

async function handleCancel() {
  if (!currentTaskId.value || cancelling.value) return;
  cancelling.value = true;
  try {
    await cancelTask(currentTaskId.value);
    // 后端会主动推 task_end/canceled 事件，前端通过 WS 收尾
  } catch (e) {
    console.error("取消任务失败：", e instanceof Error ? e.message : e);
  } finally {
    // 兜底：若 WS 没收到 cancel 事件，2s 后强制清状态
    setTimeout(() => {
      cancelling.value = false;
      if (chatSession.runningMode === "solution") {
        chatSession.setRunning(null);
      }
    }, 2000);
  }
}

/** 带鉴权的文件导出下载 */
async function downloadExport(format: "md" | "docx" | "xlsx" | "csv") {
  if (!currentTaskId.value) return;
  try {
    const { default: request } = await import("@/utils/request");
    const resp = await request.get(`/tasks/${currentTaskId.value}/export`, {
      params: { format },
      responseType: "blob",
    });
    const blob = new Blob([resp.data]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const ext = format;
    a.download = `paper.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error("导出失败：", e instanceof Error ? e.message : e);
  }
}

/** 下载完整结果包 */
async function downloadPackage() {
  if (!currentTaskId.value) return;
  try {
    const { default: request } = await import("@/utils/request");
    const resp = await request.get(`/tasks/${currentTaskId.value}/package`, {
      responseType: "blob",
    });
    const blob = new Blob([resp.data]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentTaskId.value}_results.zip`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error("打包下载失败：", e instanceof Error ? e.message : e);
  }
}

/** 论文正文（`final-` 消息）的 Markdown 全文。
 *  交付物面板据此标注哪张图真的进了正文（见 DeliverablesPanel）。 */
const paperMarkdown = computed(
  () =>
    displayMessages.value.find(
      (m) => typeof m.id === "string" && m.id.startsWith("final-"),
    )?.content ?? "",
);

/** 图表大图预览 */
const previewImage = ref<string | null>(null);

// ---- 论文阅读器 ----
const showPaperViewer = ref(false);
const paperContent = ref("");

function openPaperViewer() {
  // 从 displayMessages 中找到论文消息
  const paperMsg = displayMessages.value.find(
    (m) => typeof m.id === "string" && m.id.startsWith("final-"),
  );
  if (paperMsg?.content) {
    paperContent.value = paperMsg.content;
    showPaperViewer.value = true;
    return;
  }
  // 论文还没生成（任务在跑/失败/被取消）→ 明确告知，旧实现点了没反应
  toast(
    taskStore.isRunning
      ? "论文还在生成中，完成后可阅读全文"
      : "本任务还没有论文正文",
    "info",
  );
}

function closePaperViewer() {
  showPaperViewer.value = false;
}

/**
 * 把「当前视图」切到某个方案会话对应的任务。
 *
 * 会话与任务是 1:1（session.taskId）。切换会话必须同时换任务视图，
 * 否则 displayMessages 会把新会话的消息和上一个任务的进度气泡拼在一起，
 * 右栏也会继续显示旧任务的图表/文件（旧实现只切 activeSolutionId）。
 */
function applySessionTask(sess: ChatSession | null) {
  const storedTaskId = sess?.taskId ?? null;
  taskSessionId.value = sess?.id ?? null;

  // 同一个任务（用户只是切回来）→ 保留 WS 连接与已缓存的进度
  if (storedTaskId && storedTaskId === currentTaskId.value) return;

  currentTaskId.value = storedTaskId;
  taskFiles.value = [];
  if (!storedTaskId) {
    taskStore.clearTaskView();
    return;
  }
  taskStore.setCurrentTask(storedTaskId);
  taskStore.fetchTaskEvents(storedTaskId);
  fetchTaskFiles(storedTaskId);
  getTask(storedTaskId)
    .then((res) => {
      const t = res.data?.data ?? res.data;
      // 任务仍在跑 → 重连 WS 恢复实时进度；已完成则只做静态恢复
      if (t?.status === "running") taskStore.connectWebSocket(storedTaskId);
    })
    .catch(() => {});
}

// 会话切换（侧栏「方案」条目）→ 同步任务视图，避免跨会话串消息
watch(
  () => chatSession.activeSolutionId,
  () => applySessionTask(chatSession.activeSolutionSession),
);

// task_end 后 taskStore.isRunning=false，同步 solution 的 runningMode
watch(
  () => taskStore.isRunning,
  (running) => {
    if (!running && chatSession.runningMode === "solution") {
      chatSession.setRunning(null);
    }
  },
);

onMounted(() => {
  if (
    !chatSession.activeSolutionId &&
    chatSession.sortedSolutionSessions.length > 0
  ) {
    chatSession.switchSession(
      "solution",
      chatSession.sortedSolutionSessions[0].id,
    );
  }
  // 刷新恢复：task_id 持久化在 session 上 → 回放事件流重建动态时间线 + 交付物；
  // 任务仍在跑则重连 WS 恢复实时进度。
  applySessionTask(chatSession.activeSolutionSession);
});

// 注意：故意不在 onUnmounted 关闭 WS，避免切页导致任务进度丢失。
// WS 由 taskStore 持有，task_end 后会保持连接直到用户切换任务/显式关闭。
onBeforeUnmount(() => {});
</script>

<style scoped>
.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.25s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>