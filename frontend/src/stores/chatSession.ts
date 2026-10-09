import type {
  AgentMessage,
  AgentSegment,
  ClarifyMessage,
  Message,
  ToolMessage,
  ToolStatus,
} from "@/types/response";
import request from "@/utils/request";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

export type SessionMode = "chat" | "solution" | "learning" | "practice";

export interface ChatSession {
  id: string;
  title: string;
  mode: SessionMode;
  messages: Message[];
  createdAt: string;
  updatedAt: string;
  /** 方案模式关联的任务 id（刷新后恢复事件回放/交付物） */
  taskId?: string;
  /** 消息是否已从服务端加载（懒加载：同步时只预载最近几个会话，其余切换时再拉）。
   *  undefined = 旧版本持久化的遗留数据（有消息即视为已加载，见 needsMessageLoad） */
  messagesLoaded?: boolean;
}

/** 该会话是否需要按需拉取消息。
 *  - messagesLoaded === false：同步时明确未预载 → 要拉
 *  - undefined（旧持久化数据）：有消息视为已加载；空会话才拉一次 */
function needsMessageLoad(s: ChatSession): boolean {
  if (s.messagesLoaded !== undefined) return !s.messagesLoaded;
  return s.messages.length === 0;
}

function now() {
  return new Date().toISOString();
}

function genId() {
  return `sess_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export const useChatSessionStore = defineStore(
  "chatSession",
  () => {
    const chatSessions = ref<ChatSession[]>([]);
    const solutionSessions = ref<ChatSession[]>([]);
    const learningSessions = ref<ChatSession[]>([]);
    const practiceSessions = ref<ChatSession[]>([]);

    const activeChatId = ref<string | null>(null);
    const activeSolutionId = ref<string | null>(null);
    const activeLearningId = ref<string | null>(null);
    const activePracticeId = ref<string | null>(null);

    /** 当前正在运行的模式（仅允许一个，避免三页互串）。null = 空闲。 */
    const runningMode = ref<SessionMode | null>(null);

    function getIsRunning(mode: SessionMode) {
      return runningMode.value === mode;
    }
    function setRunning(mode: SessionMode | null) {
      runningMode.value = mode;
    }

    function getSessions(mode: SessionMode) {
      switch (mode) {
        case "chat":
          return chatSessions;
        case "solution":
          return solutionSessions;
        case "learning":
          return learningSessions;
        case "practice":
          return practiceSessions;
      }
    }

    function getActiveId(mode: SessionMode) {
      switch (mode) {
        case "chat":
          return activeChatId;
        case "solution":
          return activeSolutionId;
        case "learning":
          return activeLearningId;
        case "practice":
          return activePracticeId;
      }
    }

    function setActiveId(mode: SessionMode, id: string | null) {
      switch (mode) {
        case "chat":
          activeChatId.value = id;
          break;
        case "solution":
          activeSolutionId.value = id;
          break;
        case "learning":
          activeLearningId.value = id;
          break;
        case "practice":
          activePracticeId.value = id;
          break;
      }
    }

    const sortedChatSessions = computed(() =>
      [...chatSessions.value].sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      ),
    );
    const sortedSolutionSessions = computed(() =>
      [...solutionSessions.value].sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      ),
    );
    const sortedLearningSessions = computed(() =>
      [...learningSessions.value].sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      ),
    );
    const sortedPracticeSessions = computed(() =>
      [...practiceSessions.value].sort(
        (a, b) =>
          new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
      ),
    );

    function getSortedSessions(mode: SessionMode) {
      switch (mode) {
        case "chat":
          return sortedChatSessions;
        case "solution":
          return sortedSolutionSessions;
        case "learning":
          return sortedLearningSessions;
        case "practice":
          return sortedPracticeSessions;
      }
    }

    const activeChatSession = computed(
      () => chatSessions.value.find((s) => s.id === activeChatId.value) ?? null,
    );
    const activeSolutionSession = computed(
      () =>
        solutionSessions.value.find((s) => s.id === activeSolutionId.value) ??
        null,
    );
    const activeLearningSession = computed(
      () =>
        learningSessions.value.find((s) => s.id === activeLearningId.value) ??
        null,
    );
    const activePracticeSession = computed(
      () =>
        practiceSessions.value.find((s) => s.id === activePracticeId.value) ??
        null,
    );

    function getActiveSession(mode: SessionMode) {
      switch (mode) {
        case "chat":
          return activeChatSession;
        case "solution":
          return activeSolutionSession;
        case "learning":
          return activeLearningSession;
        case "practice":
          return activePracticeSession;
      }
    }

    const activeChatMessages = computed(
      () => activeChatSession.value?.messages ?? [],
    );
    const activeSolutionMessages = computed(
      () => activeSolutionSession.value?.messages ?? [],
    );
    const activeLearningMessages = computed(
      () => activeLearningSession.value?.messages ?? [],
    );
    const activePracticeMessages = computed(
      () => activePracticeSession.value?.messages ?? [],
    );

    function getActiveMessages(mode: SessionMode) {
      switch (mode) {
        case "chat":
          return activeChatMessages;
        case "solution":
          return activeSolutionMessages;
        case "learning":
          return activeLearningMessages;
        case "practice":
          return activePracticeMessages;
      }
    }

    /** 每个模式最多持久化的会话数，超出淘汰最旧（按 updatedAt）。 */
    const MAX_SESSIONS_PER_MODE = 60;

    function trimSessions(mode: SessionMode) {
      const list = getSessions(mode).value;
      if (list.length <= MAX_SESSIONS_PER_MODE) return;
      // 按 updatedAt 降序，保留最新 N 条，就地淘汰最旧会话
      const keepIds = new Set(
        [...list]
          .sort(
            (a, b) =>
              new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
          )
          .slice(0, MAX_SESSIONS_PER_MODE)
          .map((s) => s.id),
      );
      for (let i = list.length - 1; i >= 0; i--) {
        if (!keepIds.has(list[i].id)) list.splice(i, 1);
      }
    }

    function createSession(mode: SessionMode): string {
      const id = genId();
      const titleMap: Record<SessionMode, string> = {
        chat: "新对话",
        solution: "新方案",
        learning: "新学习",
        practice: "新练习",
      };
      const session: ChatSession = {
        id,
        title: titleMap[mode],
        mode,
        messages: [],
        createdAt: now(),
        updatedAt: now(),
        messagesLoaded: true, // 本地新建会话以本地为准，不需要回拉
      };
      getSessions(mode).value.push(session);
      setActiveId(mode, id);
      trimSessions(mode);
      void pushSessionToServer(mode, session);
      return id;
    }

    function switchSession(mode: SessionMode, id: string) {
      const list = getSessions(mode).value;
      const session = list.find((s) => s.id === id);
      if (!session) return;
      setActiveId(mode, id);
      // 懒加载：同步时只预载了最近几个会话的消息，切到未加载的会话时按需拉取
      if (needsMessageLoad(session)) void loadSessionMessages(mode, id);
    }

    /** 正在拉取消息的会话 id → loading 标记（供侧边栏转圈）。 */
    const pendingMessageLoads = ref<Record<string, boolean>>({});

    /** 按需拉取会话消息；并发去重，失败保持未加载（下次切换重试）。 */
    async function loadSessionMessages(mode: SessionMode, id: string) {
      const session = getSessions(mode).value.find((s) => s.id === id);
      if (
        !session ||
        !needsMessageLoad(session) ||
        pendingMessageLoads.value[id]
      )
        return;
      pendingMessageLoads.value[id] = true;
      try {
        const res = await request.get(`/conversations/${id}/messages`, {
          params: { limit: 2000 },
        });
        const msgs = (
          (res.data?.messages ?? []) as Array<Record<string, unknown>>
        ).map(payloadToMsg);
        // 拉取期间会话可能已被删除，取最新引用再赋值
        const target = getSessions(mode).value.find((s) => s.id === id);
        if (target) {
          target.messages = msgs;
          target.messagesLoaded = true;
        }
      } catch {
        /* 静默：保持未加载态，下次切换重试 */
      } finally {
        delete pendingMessageLoads.value[id];
      }
    }

    function deleteSession(mode: SessionMode, id: string) {
      const list = getSessions(mode).value;
      const idx = list.findIndex((s) => s.id === id);
      if (idx === -1) return;
      // 清理该会话的内联工具附件与片段流（防止 localStorage 泄漏）
      for (const m of list[idx].messages) {
        if (m.msg_type === "agent") {
          delete toolAttachments.value[m.id];
          delete agentSegments.value[m.id];
        }
      }
      list.splice(idx, 1);
      const activeId = getActiveId(mode);
      if (activeId.value === id) {
        const sorted = getSortedSessions(mode).value;
        setActiveId(mode, sorted[0]?.id ?? null);
      }
      request.delete(`/conversations/${id}`).catch(() => {});
    }

    function renameSession(mode: SessionMode, id: string, newTitle: string) {
      const list = getSessions(mode).value;
      const session = list.find((s) => s.id === id);
      if (!session) return;
      session.title = newTitle.trim() || "新对话";
      session.updatedAt = now();
      request
        .patch(`/conversations/${id}`, { title: session.title })
        .catch(() => {});
    }

    function addMessage(mode: SessionMode, sessionId: string, msg: Message) {
      const list = getSessions(mode).value;
      const session = list.find((s) => s.id === sessionId);
      if (!session) return;
      session.messages.push(msg);
      session.updatedAt = now();
      const defaultTitle: Record<SessionMode, string> = {
        chat: "新对话",
        solution: "新方案",
        learning: "新学习",
        practice: "新练习",
      };
      if (
        session.title === defaultTitle[mode] &&
        msg.msg_type === "user" &&
        msg.content
      ) {
        session.title =
          msg.content.slice(0, 30) + (msg.content.length > 30 ? "..." : "");
      }
      scheduleServerSync(mode, sessionId);
    }

    /** 流式更新同一条消息（就地累加/替换 content，或更新 streaming / thinking / status 标记）。 */
    function updateMessage(
      mode: SessionMode,
      sessionId: string,
      msgId: string,
      patch: Partial<Pick<Message, "content" | "streaming">> & {
        thinking?: string;
        status?: ToolStatus;
        output?: unknown[];
        answered?: boolean;
        error?: boolean;
        duration_ms?: number;
      },
    ) {
      const list = getSessions(mode).value;
      const session = list.find((s) => s.id === sessionId);
      if (!session) return;
      const msg = session.messages.find((m) => m.id === msgId);
      if (!msg) return;
      if (patch.content !== undefined) msg.content = patch.content;
      if (patch.streaming !== undefined) msg.streaming = patch.streaming;
      if (patch.thinking !== undefined)
        (msg as AgentMessage).thinking = patch.thinking;
      if (patch.status !== undefined)
        (msg as ToolMessage).status = patch.status;
      if (patch.output !== undefined)
        (msg as ToolMessage).output = patch.output;
      if (patch.error !== undefined) (msg as AgentMessage).error = patch.error;
      if (patch.duration_ms !== undefined)
        (msg as ToolMessage).duration_ms = patch.duration_ms;
      if (patch.answered !== undefined && "answered" in msg)
        (msg as ClarifyMessage).answered = patch.answered;
      session.updatedAt = now();
      scheduleServerSync(mode, sessionId);
    }

    function clearActive(mode: SessionMode) {
      setActiveId(mode, null);
    }

    /** 清空当前会话的全部消息(保留会话本身)。 */
    function clearSession(mode: SessionMode) {
      const session = getActiveSession(mode).value;
      if (session) {
        session.messages = [];
        session.messagesLoaded = true; // 本地已确认清空，无需回拉
        session.updatedAt = now();
        // 服务端无清空接口 → 删了重建同 id 会话再同步空消息
        void (async () => {
          try {
            await request.delete(`/conversations/${session.id}`);
            await request.post("/conversations", {
              id: session.id,
              mode,
              title: session.title,
            });
            await request.post(`/conversations/${session.id}/sync`, {
              messages: [],
            });
          } catch {
            /* 静默 */
          }
        })();
      }
    }

    // ── 工具内联附件（chat 模式，dsh 式"工具嵌在回复里"）──
    // 流式期间工具卡片不再作为独立消息行，而是挂到 agent 气泡内联渲染；
    // key 为 agent 消息 id（前端生成，全局唯一）。刻意不持久化：刷新后只保留文本。
    const toolAttachments = ref<Record<string, Message[]>>({});

    /** 把一个工具消息挂到 agent 气泡下（内联渲染，不进消息列表）。 */
    function attachTool(agentMsgId: string, toolMsg: Message) {
      if (!toolAttachments.value[agentMsgId]) {
        toolAttachments.value[agentMsgId] = [];
      }
      toolAttachments.value[agentMsgId].push(toolMsg);
    }

    /** 取 agent 气泡的内联工具消息列表（渲染用）。 */
    function getToolAttachments(agentMsgId: string): Message[] {
      return toolAttachments.value?.[agentMsgId] ?? [];
    }

    /** 清空某 agent 气泡的内联工具（重试复用气泡时调用）。 */
    function clearToolAttachments(agentMsgId: string) {
      delete toolAttachments.value[agentMsgId];
    }

    // ── 片段流（dsh 式"工具嵌在输出流的正确位置"）──
    // 文本与工具按 SSE 事件到达顺序交错记录；渲染时按序输出，
    // 而不是把所有工具卡片堆到气泡底部。不持久化：刷新后退化为全文渲染。
    const agentSegments = ref<Record<string, AgentSegment[]>>({});

    /** 追加一个片段（工具片段；文本片段用 updateTextSegment 流式累积）。 */
    function appendSegment(agentMsgId: string, seg: AgentSegment) {
      if (!agentSegments.value[agentMsgId]) {
        agentSegments.value[agentMsgId] = [];
      }
      agentSegments.value[agentMsgId].push(seg);
    }

    /** 把文本增量拼进最后一个文本片段；若最后不是文本（或无），追加新的文本片段。 */
    function updateTextSegment(agentMsgId: string, delta: string) {
      if (!agentSegments.value[agentMsgId]) {
        agentSegments.value[agentMsgId] = [];
      }
      const segs = agentSegments.value[agentMsgId];
      const last = segs[segs.length - 1];
      if (last && last.kind === "text") {
        last.text += delta;
      } else {
        segs.push({ kind: "text", text: delta });
      }
    }

    /** 取 agent 气泡的片段流（渲染用）。 */
    function getAgentSegments(agentMsgId: string): AgentSegment[] {
      return agentSegments.value?.[agentMsgId] ?? [];
    }

    /** 清空某 agent 气泡的片段流（重试复用气泡时调用）。 */
    function clearAgentSegments(agentMsgId: string) {
      delete agentSegments.value[agentMsgId];
    }

    /** 显式新建会话（不清空当前会话）。 */
    function newSession(mode: SessionMode): string {
      return createSession(mode);
    }

    // ── 服务端会话持久化(/api/conversations,SQLite)────────────
    // 启动拉取合并(服务端为准)+ 变更节流同步(失败静默,本地 localStorage 仍可用)。
    const syncTimers = new Map<string, number>();

    function msgToPayload(m: Message) {
      return {
        id: m.id,
        msg_type: m.msg_type,
        content: m.content ?? null,
        tool_name: m.msg_type === "tool" ? m.tool_name : null,
        input: m.msg_type === "tool" ? m.input : null,
        output: m.msg_type === "tool" ? m.output : null,
        status: m.msg_type === "tool" ? (m.status ?? null) : null,
        thinking: m.msg_type === "agent" ? (m.thinking ?? null) : null,
        agent_type: m.msg_type === "agent" ? (m.agent_type ?? null) : null,
        answered: m.msg_type === "clarify" ? (m.answered ?? null) : null,
        streaming: m.streaming ?? null,
        created_at: m.created_at ?? null,
      };
    }

    function payloadToMsg(p: Record<string, unknown>): Message {
      const msg: Record<string, unknown> = {
        id: p.id,
        msg_type: p.msg_type,
        content: p.content ?? null,
        created_at: p.created_at,
      };
      for (const key of [
        "tool_name",
        "input",
        "output",
        "status",
        "thinking",
        "agent_type",
      ]) {
        if (p[key] !== null && p[key] !== undefined) msg[key] = p[key];
      }
      if (p.answered) msg.answered = true;
      // 不恢复 streaming 标记：能从持久化里读出来的流必然已死，
      // 恢复它会让旧气泡刷新后永久卡在"生成中"（审查 P1）
      return msg as unknown as Message;
    }

    /** 整会话推送到服务端(会话创建幂等 + 消息 INSERT OR REPLACE 幂等)。 */
    async function pushSessionToServer(
      mode: SessionMode,
      session: ChatSession,
    ) {
      try {
        await request.post("/conversations", {
          id: session.id,
          mode,
          title: session.title,
        });
        await request.post(`/conversations/${session.id}/sync`, {
          messages: session.messages.map(msgToPayload),
        });
      } catch {
        /* 静默: 离线/未启动后端时保持本地可用 */
      }
    }

    /** 节流同步(流式期间 updateMessage 高频,合并到 800ms 尾调用)。 */
    function scheduleServerSync(mode: SessionMode, sessionId: string) {
      const key = `${mode}:${sessionId}`;
      const prev = syncTimers.get(key);
      if (prev !== undefined) window.clearTimeout(prev);
      syncTimers.set(
        key,
        window.setTimeout(() => {
          syncTimers.delete(key);
          const session = getSessions(mode).value.find(
            (s) => s.id === sessionId,
          );
          if (session) void pushSessionToServer(mode, session);
        }, 800),
      );
    }

    /** 启动时从服务端拉取该模式会话(服务端为准,本地独有会话合并并补推)。 */
    async function syncModeFromServer(mode: SessionMode) {
      try {
        const res = await request.get("/conversations", {
          params: { mode, limit: 60 },
        });
        const convs = (res.data?.conversations ?? []) as Array<{
          id: string;
          title: string;
          mode?: string;
          created_at: string;
          updated_at: string;
        }>;
        if (convs.length === 0) {
          // 服务端空 → 本地历史迁移上去
          for (const s of getSessions(mode).value) {
            void pushSessionToServer(mode, s);
          }
          return;
        }
        const localBefore = [...getSessions(mode).value];
        // 懒加载：只对最近 N 个会话并行预载消息，其余留空、切换时按需拉取。
        // 历史：此前对全部会话（上限 60）串行拉消息（每个 limit 2000），
        // 四个模式合计最坏 240+ 个串行 round trip + 几十 MB JSON，
        // 是进页面卡顿的主因。预载数量覆盖「恢复最近会话」的常规路径即可。
        const PRELOAD_MESSAGE_SESSIONS = 3;
        const byRecent = [...convs].sort(
          (a, b) =>
            new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
        );
        const preloadIds = new Set(
          byRecent.slice(0, PRELOAD_MESSAGE_SESSIONS).map((c) => c.id),
        );
        const loaded: ChatSession[] = await Promise.all(
          convs.map(async (c) => {
            let messages: Message[] = [];
            let messagesLoaded = false;
            if (preloadIds.has(c.id)) {
              try {
                const msgsRes = await request.get(
                  `/conversations/${c.id}/messages`,
                  { params: { limit: 2000 } },
                );
                messages = (
                  (msgsRes.data?.messages ?? []) as Array<
                    Record<string, unknown>
                  >
                ).map(payloadToMsg);
                messagesLoaded = true;
              } catch {
                /* 单会话失败不阻塞其余，保持未加载态下次重试 */
              }
            }
            return {
              id: c.id,
              title: c.title,
              mode: (c.mode as SessionMode) ?? mode,
              messages,
              createdAt: c.created_at,
              updatedAt: c.updated_at,
              messagesLoaded,
            };
          }),
        );
        const serverIds = new Set(loaded.map((s) => s.id));
        const localOnly = localBefore.filter((s) => !serverIds.has(s.id));
        const list = getSessions(mode);
        list.value = [...loaded, ...localOnly].sort(
          (a, b) =>
            new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
        );
        const active = getActiveId(mode).value;
        setActiveId(
          mode,
          list.value.some((s) => s.id === active)
            ? active
            : (list.value[0]?.id ?? null),
        );
        for (const s of localOnly) void pushSessionToServer(mode, s);
      } catch {
        /* 静默: 后端不可用回退 localStorage */
      }
    }

    // store 首次创建时后台同步四个模式(浏览器环境)
    if (typeof window !== "undefined") {
      for (const m of [
        "chat",
        "solution",
        "learning",
        "practice",
      ] as SessionMode[]) {
        void syncModeFromServer(m);
      }
    }

    return {
      chatSessions,
      solutionSessions,
      learningSessions,
      practiceSessions,
      activeChatId,
      activeSolutionId,
      activeLearningId,
      activePracticeId,
      runningMode,
      sortedChatSessions,
      sortedSolutionSessions,
      sortedLearningSessions,
      sortedPracticeSessions,
      activeChatSession,
      activeSolutionSession,
      activeLearningSession,
      activePracticeSession,
      activeChatMessages,
      activeSolutionMessages,
      activeLearningMessages,
      activePracticeMessages,
      createSession,
      newSession,
      switchSession,
      loadSessionMessages,
      pendingMessageLoads,
      deleteSession,
      renameSession,
      addMessage,
      updateMessage,
      clearActive,
      clearSession,
      getSessions,
      getActiveId,
      getSortedSessions,
      getActiveSession,
      getActiveMessages,
      getIsRunning,
      setRunning,
      attachTool,
      getToolAttachments,
      clearToolAttachments,
      appendSegment,
      updateTextSegment,
      getAgentSegments,
      clearAgentSegments,
    };
  },
  {
    persist: {
      key: "mma-chat-sessions",
      storage: localStorage,
      pick: [
        "chatSessions",
        "solutionSessions",
        "learningSessions",
        "practiceSessions",
        "activeChatId",
        "activeSolutionId",
        "activeLearningId",
        "activePracticeId",
        // 工具内联附件 + 片段流：刷新后恢复工具卡片与交错渲染
        // （agent 消息只存了文本，工具卡片与位置信息由这两份状态补全）
        "toolAttachments",
        "agentSegments",
      ],
    },
  },
);
