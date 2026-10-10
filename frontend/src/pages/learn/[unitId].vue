<template>
  <div class="flex h-full bg-background">
    <!-- 左侧栏: 可折叠(折叠按钮固定在底部) -->
    <div :class="leftOpen ? 'w-56' : 'w-10'" class="shrink-0 border-r flex flex-col transition-all duration-200">
      <div v-if="leftOpen" class="flex-1 overflow-y-auto min-h-0">
        <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground px-3 py-2.5 border-b flex items-center gap-1.5"><List class="h-3 w-3" />目录</p>
        <div class="py-1">
          <button v-for="h in headings" :key="h.id"
            class="block w-full text-left px-3 py-1 text-xs transition-colors hover:bg-accent/50 truncate"
            :class="activeHeading === h.id ? 'text-primary font-medium bg-primary/5' : 'text-muted-foreground'"
            :style="{ paddingLeft: (h.level * 8) + 'px' }" @click="scrollToHeading(h.id)">{{ h.text }}</button>
          <div v-if="headings.length === 0" class="px-3 py-4 text-[11px] text-muted-foreground text-center">暂无目录</div>
        </div>
      </div>
      <!-- 收起态占位,保证按钮不跳到顶部 -->
      <div v-else class="flex-1" />
      <button class="flex shrink-0 items-center justify-center border-t py-2 hover:bg-accent/50 transition-colors" @click="leftOpen = !leftOpen" :title="leftOpen ? '折叠侧栏' : '展开侧栏'">
        <PanelLeftOpen v-if="leftOpen" class="h-3.5 w-3.5 text-muted-foreground" />
        <PanelLeft v-else class="h-3.5 w-3.5 text-muted-foreground" />
      </button>
    </div>

    <!-- 中间+右侧 -->
    <div class="flex-1 flex flex-col min-w-0 min-h-0">
      <div class="flex items-center justify-between border-b px-4 py-2 shrink-0 bg-muted/20">
        <div class="flex items-center gap-2">
          <button class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" @click="$router.push('/learn')"><ArrowLeft class="h-4 w-4" />返回</button>
          <span class="text-muted-foreground text-sm">/</span>
          <span class="font-display font-medium text-sm truncate">{{ unit?.title ?? '加载中...' }}</span>
          <span v-if="unit" class="font-mono text-[10px] px-1.5 py-0.5 rounded border shrink-0" :class="difficultyBadge">{{ difficultyLabel }}</span>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <span class="font-mono text-[10px] text-muted-foreground hidden sm:inline">⏱ {{ unit?.estimated_minutes ?? '--' }}分钟</span>
          <button class="font-mono text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1" @click="chatPanel?.toggle()"><MessageCircle class="h-3.5 w-3.5" />{{ chatPanel?.open ? '收起助手' : '问AI' }}</button>
        </div>
      </div>

      <!-- 加载骨架屏: 左侧目录条 + 正文段落,避免整页空白转圈 -->
      <div v-if="store.loading" class="flex-1 min-h-0 flex gap-8 overflow-hidden p-8">
        <div class="hidden w-52 shrink-0 space-y-2.5 md:block">
          <Skeleton v-for="i in 7" :key="i" class="h-3.5" :class="i % 3 === 0 ? 'w-2/3' : 'w-full'" />
        </div>
        <div class="flex-1 space-y-3.5 overflow-hidden">
          <Skeleton class="h-7 w-2/3" />
          <Skeleton class="h-4 w-full" />
          <Skeleton class="h-4 w-full" />
          <Skeleton class="h-4 w-5/6" />
          <Skeleton class="mt-4 h-4 w-full" />
          <Skeleton class="h-4 w-3/4" />
          <Skeleton class="mt-4 h-28 w-full" />
          <Skeleton class="h-4 w-full" />
          <Skeleton class="h-4 w-2/3" />
        </div>
      </div>
      <div v-else-if="store.error" class="flex-1 flex items-center justify-center"><p class="text-sm text-destructive">{{ store.error }}</p></div>

      <ChatPanel
        v-else-if="unit"
        ref="chatPanel"
        storage-key="unit-chat"
        :default-width="400"
        button-label="问AI"
        :collapse-below="1024"
        class="flex-1 min-h-0"
      >
        <template #main>
          <LearningDoc ref="docRef" :markdown="docMarkdown" :unit-id="unit.unit_id"
            :on-ask-a-i="handleAskAI"
            @headings-change="headings = $event" @scroll-section="activeHeading = $event">
            <UnitQuizBlock :unit-id="unit.unit_id" @complete="onQuizComplete" />
          </LearningDoc>
        </template>

        <ChatArea
          :messages="chatSession.activeLearningMessages"
          :is-running="chatSession.getIsRunning('learning')"
          :empty-text="`有问题随时问我`" :empty-subtext="'选中文档文字 → 点「问AI」快速提问'"
          :input-placeholder="`向${agentName}提问...`"
          :prefill-text="prefillText"
          :session-title="chatSession.activeLearningSession?.title"
          cancellable @send="handleSend" @cancel="cancelStream" @retry="retryLast"
          @clear="chatSession.clearSession('learning')"
          @new-session="chatSession.newSession('learning')" />
      </ChatPanel>

    </div>

  </div>
</template>

<script setup lang="ts">
import ChatArea from "@/components/ChatArea.vue";
// biome-ignore lint/style/useImportType: Vue 组件注册需要值导入,type-only 会导致运行期组件解析失败
import LearningDoc from "@/components/LearningDoc.vue";
import UnitQuizBlock from "@/components/UnitQuizBlock.vue";
// biome-ignore lint/style/useImportType: Vue 组件注册需要值导入,type-only 会导致运行期组件解析失败
import ChatPanel from "@/components/chat/ChatPanel.vue";
import { Skeleton } from "@/components/ui/skeleton";
import { useStreamChat } from "@/composables/useStreamChat";
import { toast } from "@/composables/useToast";
import { useChatSessionStore } from "@/stores/chatSession";
import { useLearningStore } from "@/stores/learning";
import {
  ArrowLeft,
  Blocks,
  Compass,
  List,
  type LucideIcon,
  MessageCircle,
  Microscope,
  PanelLeft,
  PanelLeftOpen,
  PenLine,
  ShieldCheck,
  Terminal,
} from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const store = useLearningStore();
const chatSession = useChatSessionStore();
const { handleUserSend, restoreLatestSession, cancelStream, retryLast } =
  useStreamChat("learning", "learning");

const docRef = ref<InstanceType<typeof LearningDoc>>();
const chatPanel = ref<InstanceType<typeof ChatPanel>>();
// 窄屏挂载时默认收起目录(单向,不与用户争夺)
const leftOpen = ref(
  typeof window !== "undefined" ? window.innerWidth >= 1280 : true,
);
const headings = ref<{ id: string; text: string; level: number }[]>([]);
const activeHeading = ref("");
const prefillText = ref("");

// ── 聊天面板缩放收起已统一到 ChatPanel 组件 ──────────

// ── 问AI ───────────────────────────────────────────

function handleAskAI(text: string, section: string) {
  chatPanel.value?.expand();
  prefillText.value = `关于「${section || unit.value?.title || ""}」中的这段话：\n\n> ${text}\n\n请帮我解释一下。`;
}

// ── 其他 ───────────────────────────────────────────

const unit = computed(() => store.currentUnit);
const unitId = computed(() => route.params.unitId as string);
const agentMap: Record<string, { icon: LucideIcon; name: string }> = {
  analyst: { icon: Microscope, name: "分析师" },
  modeler: { icon: Blocks, name: "建模师" },
  solver: { icon: Terminal, name: "求解器" },
  verifier: { icon: ShieldCheck, name: "检验员" },
  editor: { icon: PenLine, name: "编辑" },
};
const agentInfo = computed(
  () =>
    agentMap[unit.value?.primary_agent ?? ""] ?? {
      icon: Compass,
      name: "导航员",
    },
);
const agentName = computed(() => agentInfo.value.name);
const difficultyLabel = computed(
  () =>
    (
      ({
        beginner: "入门",
        intermediate: "进阶",
        advanced: "高阶",
        competition: "竞赛",
      }) as Record<string, string>
    )[unit.value?.difficulty ?? "beginner"],
);
const difficultyBadge = computed(
  () =>
    (
      ({
        beginner: "border-emerald-200 text-emerald-700 bg-emerald-50",
        intermediate: "border-amber-200 text-amber-700 bg-amber-50",
        advanced: "border-red-200 text-red-700 bg-red-50",
        competition: "border-purple-200 text-purple-700 bg-purple-50",
      }) as Record<string, string>
    )[unit.value?.difficulty ?? "beginner"],
);
const unitContext = computed(() => {
  const u = unit.value;
  if (!u) return undefined;
  return {
    unit_id: u.unit_id,
    title: u.title,
    unit_type: u.type === "knowledge" ? "知识讲解" : "练习",
    difficulty: u.difficulty,
    method_category: u.method_category || "通用",
    tags: u.tags?.join(", ") ?? "",
    primary_agent: u.primary_agent ?? "modeler",
    estimated_minutes: String(u.estimated_minutes ?? 30),
  };
});

function handleSend(text: string) {
  handleUserSend(text, undefined, unitContext.value);
}

function onQuizComplete(p: { correct: number; total: number }) {
  toast(
    p.correct === p.total
      ? `自测全对: ${p.correct}/${p.total}`
      : `自测完成: ${p.correct}/${p.total} 正确`,
    p.correct === p.total ? "success" : "info",
  );
}
function scrollToHeading(id: string) {
  docRef.value?.scrollToHeading(id);
  activeHeading.value = id;
}

onMounted(() => {
  if (unitId.value) store.loadUnit(unitId.value);
  restoreLatestSession();
});
watch(
  () => route.params.unitId,
  (id) => {
    if (id) {
      store.loadUnit(id as string);
      headings.value = [];
      activeHeading.value = "";
    }
  },
);

const docMarkdown = computed(
  () =>
    unit.value?.content_md ||
    `# ${unit.value?.title || "学习内容"}\n\n学习资料正在准备中。`,
);
</script>
