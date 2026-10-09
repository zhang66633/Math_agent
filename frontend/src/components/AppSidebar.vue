<template>
  <aside
    data-tour="sidebar"
    :class="[
      collapsed ? 'w-12' : '',
      'relative flex flex-col border-r bg-background h-screen sticky top-0 shrink-0 overflow-hidden',
      dragging ? '' : 'transition-[width] duration-200',
    ]"
    :style="collapsed ? undefined : { width: `${navWidth}px` }"
  >
    <!-- 头部：Logo 行，右上角收起按钮（article_agent 几何：24px 图标 + 折叠态居中接管，位置零跳动） -->
    <div v-if="!collapsed" class="flex h-14 items-center justify-between border-b pl-3 pr-2 shrink-0">
      <button class="flex items-center gap-2.5 min-w-0" title="回到首页" @click="navigate('/')">
        <div class="flex h-6 w-6 items-center justify-center border border-border rounded-sm shrink-0">
          <span class="font-display text-sm font-medium leading-none">M</span>
        </div>
        <span class="font-display text-sm font-medium tracking-tight truncate">{{ APP_NAME }}</span>
      </button>
      <button
        class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        title="折叠侧栏"
        aria-label="折叠侧栏"
        @click="setCollapsed(true)"
      >
        <PanelLeftClose class="h-3.5 w-3.5" />
      </button>
    </div>
    <button
      v-else
      class="flex h-14 items-center justify-center border-b shrink-0 cursor-pointer"
      title="展开侧栏"
      aria-label="展开侧栏"
      @click="setCollapsed(false)"
    >
      <div class="flex h-6 w-6 items-center justify-center border border-border rounded-sm shrink-0">
        <span class="font-display text-sm font-medium leading-none">M</span>
      </div>
    </button>

    <!-- 展开态: 完整导航(主区域,可滚动,学习入口优先) -->
    <nav v-if="!collapsed" class="flex-1 overflow-y-auto py-3 min-h-0">
      <button :class="[NAV_ITEM, isNavActive('/') ? 'text-foreground font-medium' : 'text-muted-foreground hover:text-foreground hover:bg-accent/30']" @click="navigate('/')">
        <span v-if="isNavActive('/')" class="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 bg-primary" />
        <Home class="h-4 w-4 shrink-0" />
        <span :class="isNavActive('/') ? 'font-display font-medium' : ''">首页</span>
      </button>
      <div v-for="group in visibleGroups" :key="group.label" class="mt-1">
        <!-- 静态小节标签(图标+汉字;两个组头常亮高亮,不随页面切换) -->
        <p class="relative flex items-center gap-2 w-full px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wider text-foreground font-medium">
          <span class="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-0.5 bg-primary" />
          <component :is="group.icon" class="h-3.5 w-3.5 shrink-0 text-primary" />
          {{ group.label }}
        </p>
        <div class="space-y-0.5">
          <button v-for="(item, i) in group.items" :key="item.path"
            :class="[NAV_ITEM, isNavActive(item.path) ? 'text-foreground font-medium' : 'text-muted-foreground hover:text-foreground hover:bg-accent/30']" @click="navigate(item.path)">
            <span v-if="isNavActive(item.path)" class="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-px bg-primary" />
            <component :is="item.icon" class="h-4 w-4 shrink-0 opacity-60" />
            <span :class="isNavActive(item.path) ? 'font-display font-medium' : ''">{{ item.label }}</span>
          </button>
        </div>
      </div>
    </nav>

    <!-- 聊天记录(跨模式汇总,固定位置,空时占位保持布局稳定) -->
    <div v-if="!collapsed" class="border-t py-2 shrink-0 max-h-40 overflow-y-auto min-h-0">
      <p class="px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground/60">AI 聊天记录</p>
      <p v-if="sessionList.length === 0" class="px-2.5 py-2 text-[11px] text-muted-foreground/50">
        暂无聊天记录
      </p>
      <TransitionGroup name="session-list">
        <div
          v-for="s in sessionList"
          :key="s.session.id"
          class="group relative flex w-full items-center gap-2 py-1 pr-2 pl-2.5 text-sm cursor-pointer transition-all duration-200"
          :class="isActiveSession(s) ? 'text-foreground bg-accent/50' : 'text-muted-foreground hover:text-foreground hover:bg-accent/30'"
          @click="switchTo(s)"
        >
          <Transition name="indicator">
            <div
              v-if="isActiveSession(s)"
              class="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 bg-primary rounded-r"
            />
          </Transition>
          <template v-if="editing?.id === s.session.id">
            <input
              v-model="editingTitle"
              class="flex-1 text-xs bg-background border border-primary/30 rounded px-1.5 py-0.5 outline-none"
              @keyup.enter="confirmRename"
              @keyup.esc="cancelRename"
              @click.stop
              autofocus
            />
          </template>
          <template v-else>
            <span class="shrink-0 rounded bg-muted px-1 py-px font-mono text-[9px] text-muted-foreground/80">
              {{ modeBadge[s.mode] }}
            </span>
            <span class="truncate flex-1 text-xs">{{ s.session.title }}</span>
          </template>
          <div class="flex items-center gap-1 shrink-0">
            <Loader2
              v-if="chatSession.pendingMessageLoads[s.session.id]"
              class="h-3 w-3 shrink-0 animate-spin text-muted-foreground"
              title="正在加载消息"
            />
            <button
              v-if="editing?.id !== s.session.id"
              class="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm opacity-0 group-hover:opacity-100 hover:bg-primary/10 hover:text-primary transition-all"
              @click.stop="startRename(s)"
              title="重命名"
            >
              <Pencil class="h-3 w-3" />
            </button>
            <button
              v-if="editing?.id === s.session.id"
              class="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm opacity-100 hover:bg-primary/10 hover:text-primary transition-all"
              @click.stop="confirmRename"
              title="确认"
            >
              <Check class="h-3 w-3" />
            </button>
            <button
              class="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive transition-all"
              @click.stop="removeSession(s)"
              title="删除"
            >
              <X class="h-3 w-3" />
            </button>
          </div>
        </div>
      </TransitionGroup>
    </div>

    <!-- 折叠态: 仅图标。分组标题行用 invisible 占位（article_agent 同款），
         保证每个图标与展开态同项垂直位置完全一致 -->
    <nav v-else class="flex-1 overflow-y-auto py-3 min-h-0 flex flex-col px-2.5">
      <button
        class="flex h-9 items-center rounded-md transition-colors shrink-0"
        :class="isNavActive('/') ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:text-foreground hover:bg-accent/30'"
        :title="'首页'"
        @click="navigate('/')"
      >
        <Home class="h-4 w-4" />
      </button>
      <div v-for="group in visibleGroups" :key="group.label" class="mt-1 shrink-0">
        <!-- 分区占位：折叠态用圆点分隔（紧凑，不撑大空位） -->
        <div class="flex justify-center py-1.5" aria-hidden="true">
          <span class="h-1 w-1 rounded-full bg-muted-foreground/40" />
        </div>
        <div class="space-y-0.5">
          <button
            v-for="item in group.items"
            :key="item.path"
            class="flex h-9 items-center rounded-md transition-colors"
            :class="isNavActive(item.path) ? 'text-primary bg-primary/10' : 'text-muted-foreground hover:text-foreground hover:bg-accent/30'"
            :title="item.label"
            @click="navigate(item.path)"
          >
            <component :is="item.icon" class="h-4 w-4" />
          </button>
        </div>
      </div>
    </nav>

    <!-- 底部固定项(技术配置降权: 小字+弱化) -->
    <div v-if="!collapsed" class="border-t py-1.5 shrink-0">
      <button v-for="item in bottomItems" :key="item.path"
        class="group relative flex w-full items-center gap-3 py-1.5 pr-4 pl-2.5 text-xs transition-colors"
        :class="isNavActive(item.path) ? 'text-foreground font-medium' : 'text-muted-foreground/70 hover:text-foreground hover:bg-accent/30'" @click="navigate(item.path)">
        <span v-if="isNavActive(item.path)" class="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-0.5 bg-primary" />
        <component :is="item.icon" class="h-3.5 w-3.5 shrink-0 opacity-60" />
        <span :class="isNavActive(item.path) ? 'font-display font-medium' : ''">{{ item.label }}</span>
      </button>
      <!-- 新手功能导览入口: 随时可重看完整导览 -->
      <button
        class="flex w-full items-center gap-3 py-1.5 pr-4 pl-2.5 text-xs transition-colors text-muted-foreground/70 hover:text-foreground hover:bg-accent/30"
        @click="guidedTour.start()"
      >
        <Compass class="h-3.5 w-3.5 shrink-0 opacity-60" />
        <span>功能导览</span>
      </button>
    </div>

    <div v-if="!collapsed" class="border-t px-3 py-3 shrink-0">
      <VersionSwitcher />
    </div>

    <!-- 页脚状态行（article_agent 风格：mono 小字） -->
    <div v-if="!collapsed" class="border-t px-2.5 py-2 shrink-0">
      <p class="font-mono text-[10px] text-muted-foreground/60 truncate">
        {{ auth.displayName }}
      </p>
    </div>

    <!-- 拖拽分隔线（article_agent 风格：5px 抓取区，hover 高亮，键盘 ←/→ 调整） -->
    <div
      v-if="!collapsed"
      class="absolute inset-y-0 right-0 z-10 w-[5px] cursor-col-resize group outline-none"
      role="separator"
      aria-orientation="vertical"
      tabindex="0"
      title="拖动调整宽度；聚焦后可用 ←/→ 调整"
      @mousedown="beginDrag"
      @keydown="dragKey"
    >
      <div
        class="absolute inset-y-0 left-1/2 -translate-x-1/2 w-[3px] bg-transparent transition-colors"
        :class="dragging ? 'bg-primary/60' : 'group-hover:bg-primary/40 group-focus-visible:bg-primary/40'"
      />
    </div>
  </aside>
</template>

<script setup lang="ts">
import VersionSwitcher from "@/components/VersionSwitcher.vue";
import { useGuidedTour } from "@/composables/useGuidedTour";
import { bottomItems, learnGroup, paperGroup } from "@/config/navItems";
import { NAV_ITEM } from "@/config/styles";
import { useAuthStore } from "@/stores/auth";
import {
  type ChatSession,
  type SessionMode,
  useChatSessionStore,
} from "@/stores/chatSession";
import { APP_NAME } from "@/types/const";
import {
  Check,
  Compass,
  Home,
  Loader2,
  PanelLeftClose,
  Pencil,
  X,
} from "lucide-vue-next";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

// ── 侧栏宽度（article_agent 风格：可拖拽 + localStorage 记忆）──
const NAV_MIN = 200;
const NAV_MAX = 340;
const W_KEY = "mma.navWidth";

function readNavWidth(): number {
  try {
    const v = Number.parseInt(localStorage.getItem(W_KEY) || "", 10);
    if (!Number.isNaN(v)) return Math.max(NAV_MIN, Math.min(NAV_MAX, v));
  } catch {
    /* ignore */
  }
  return 256;
}

const navWidth = ref(readNavWidth());
const dragging = ref(false);

/** 拖拽调整侧栏宽度 */
function beginDrag(e: MouseEvent) {
  e.preventDefault();
  dragging.value = true;
  const startX = e.clientX;
  const startW = navWidth.value;
  const onMove = (ev: MouseEvent) => {
    const w = startW + (ev.clientX - startX);
    navWidth.value = Math.max(NAV_MIN, Math.min(NAV_MAX, w));
  };
  const onUp = () => {
    dragging.value = false;
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    try {
      localStorage.setItem(W_KEY, String(navWidth.value));
    } catch {
      /* ignore */
    }
  };
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
}

/** 键盘调整宽度（分隔线聚焦后 ←/→） */
function dragKey(e: KeyboardEvent) {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  e.preventDefault();
  const step = e.key === "ArrowLeft" ? -20 : 20;
  navWidth.value = Math.max(NAV_MIN, Math.min(NAV_MAX, navWidth.value + step));
  try {
    localStorage.setItem(W_KEY, String(navWidth.value));
  } catch {
    /* ignore */
  }
}

const auth = useAuthStore();
const guidedTour = useGuidedTour();

const router = useRouter();
const route = useRoute();
const chatSession = useChatSessionStore();

const editing = ref<{ id: string; mode: SessionMode } | null>(null);
const editingTitle = ref("");

// ── 折叠状态：localStorage 持久化（防路由跳转/组件重挂/刷新时状态重置）──
const C_KEY = "mma.sidebarCollapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(C_KEY) === "1";
  } catch {
    return false;
  }
}

const collapsed = ref(readCollapsed());

function setCollapsed(v: boolean) {
  collapsed.value = v;
  try {
    localStorage.setItem(C_KEY, v ? "1" : "0");
  } catch {
    /* ignore */
  }
}

// ── 导航分组逻辑 ─────────────────────────────────────

const allGroups = [paperGroup, learnGroup];

const visibleGroups = computed(() => allGroups);

// ── 会话逻辑(跨模式汇总,不再随页面切换) ──────────────

const MODES: SessionMode[] = ["chat", "solution", "learning", "practice"];
const modeBadge: Record<SessionMode, string> = {
  chat: "对话",
  solution: "方案",
  learning: "学习",
  practice: "练习",
};
const modeRoute: Record<SessionMode, string> = {
  chat: "/chat",
  solution: "/solution",
  learning: "/learn",
  practice: "/practice",
};

interface SessionRow {
  session: ChatSession;
  mode: SessionMode;
}

const sessionList = computed<SessionRow[]>(() => {
  const all: SessionRow[] = [];
  for (const m of MODES) {
    for (const s of chatSession.getSessions(m).value) {
      all.push({ session: s, mode: m });
    }
  }
  return all
    .sort(
      (a, b) =>
        new Date(b.session.updatedAt).getTime() -
        new Date(a.session.updatedAt).getTime(),
    )
    .slice(0, 12);
});

function isActiveSession(row: SessionRow): boolean {
  return chatSession.getActiveId(row.mode).value === row.session.id;
}

/** 点击: 激活该模式会话;当前不在该模式页面时跳转过去 */
function switchTo(row: SessionRow) {
  chatSession.switchSession(row.mode, row.session.id);
  const path = route.path;
  const onModePage =
    row.mode === "learning"
      ? path.startsWith("/learn")
      : path.startsWith(modeRoute[row.mode]);
  if (!onModePage) router.push(modeRoute[row.mode]);
}

function removeSession(row: SessionRow) {
  const wasActive = isActiveSession(row);
  chatSession.deleteSession(row.mode, row.session.id);
  if (wasActive) {
    chatSession.clearActive(row.mode);
  }
}

function startRename(row: SessionRow) {
  editing.value = { id: row.session.id, mode: row.mode };
  editingTitle.value = row.session.title;
}

function confirmRename() {
  if (editing.value) {
    chatSession.renameSession(
      editing.value.mode,
      editing.value.id,
      editingTitle.value,
    );
    editing.value = null;
    editingTitle.value = "";
  }
}

function cancelRename() {
  editing.value = null;
  editingTitle.value = "";
}

function isNavActive(path: string): boolean {
  if (path === "/") return route.path === "/";
  // 精确匹配避免 /learn 匹配到 / 等
  if (path.startsWith("/learn")) return route.path.startsWith("/learn");
  if (path.startsWith("/practice")) return route.path.startsWith("/practice");
  if (path.startsWith("/progress")) return route.path.startsWith("/progress");
  if (path.startsWith("/knowledge")) return route.path.startsWith("/knowledge");
  if (path.startsWith("/archive")) return route.path.startsWith("/archive");
  if (path.startsWith("/apikeys")) return route.path.startsWith("/apikeys");
  if (path.startsWith("/settings")) return route.path.startsWith("/settings");
  // 以下路由需要在精确匹配之前做前缀匹配（/chat 不会与 / 冲突）
  if (path === "/chat") return route.path.startsWith("/chat");
  if (path === "/teach") return route.path.startsWith("/teach");
  if (path === "/solution") return route.path.startsWith("/solution");
  return false;
}

function navigate(path: string) {
  router.push(path);
}
</script>

<style scoped>
.session-list-move {
  transition: transform 0.3s ease;
}

.session-list-enter-active,
.session-list-leave-active {
  transition: opacity 0.25s ease, height 0.3s ease, margin 0.3s ease, padding 0.3s ease;
}

.session-list-enter-from {
  opacity: 0;
  transform: translateX(-8px);
}

.session-list-leave-to {
  opacity: 0;
  height: 0 !important;
  margin-top: 0 !important;
  margin-bottom: 0 !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  overflow: hidden;
}

.indicator-enter-active,
.indicator-leave-active {
  transition: all 0.2s ease;
}

.indicator-enter-from,
.indicator-leave-to {
  opacity: 0;
  transform: translateX(-4px) scaleY(0.5);
}
</style>
