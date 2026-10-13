<template>
  <div class="flex flex-col h-full relative">
    <!-- 顶部工具栏 -->
    <ChatToolbar
      v-if="showToolbar"
      :title="sessionTitle"
      :messages-count="messages.length"
      @new-session="$emit('new-session')"
      @clear="$emit('clear')"
    />

    <!-- 消息区域 — 虚拟滚动 -->
    <div ref="scrollRef" class="flex-1 overflow-y-auto px-4 sm:px-8 py-6">
      <slot name="progress" />

      <!-- 空状态 -->
      <div v-if="messages.length === 0 && !isRunning" class="flex flex-col justify-center h-full max-w-md mx-auto px-4">
        <p class="font-display text-xl text-muted-foreground">{{ emptyText }}</p>
        <p class="text-sm text-muted-foreground/70 mt-1">{{ emptySubtext }}</p>
        <!-- 快捷提问(opt-in,不传不渲染) -->
        <div v-if="quickActions.length > 0" class="mt-4 flex flex-wrap gap-2">
          <button
            v-for="a in quickActions"
            :key="a.label"
            class="cursor-pointer rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary"
            @click="$emit('send', a.text)"
          >
            {{ a.label }}
          </button>
        </div>
      </div>

      <!-- 连接中骨架 -->
      <div v-if="isConnecting" class="space-y-4">
        <div v-for="i in 2" :key="i" class="flex items-start gap-3 animate-pulse">
          <div class="h-8 w-8 rounded-sm border border-border" />
          <div class="space-y-2 flex-1">
            <div class="h-3 bg-muted rounded w-1/4" />
            <div class="h-3 bg-muted rounded w-3/4" />
          </div>
        </div>
      </div>

      <!-- 虚拟滚动容器 -->
      <div
        v-if="messages.length > 0"
        :style="{ height: `${virtualizer.getTotalSize()}px`, width: '100%', position: 'relative' }"
      >
        <div
          v-for="item in virtualizer.getVirtualItems()"
          :key="String(item.key)"
          :ref="(el) => measureElement(el as HTMLElement)"
          :data-index="item.index"
          :style="{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            transform: `translateY(${item.start}px)`,
          }"
        >
          <Bubble
            :message="messages[item.index]"
            :is-last="item.index === messages.length - 1"
            :fold-tool-images="foldToolImages"
            @open-paper="$emit('openPaper')"
            @retry="$emit('retry')"
          />
        </div>
      </div>

      <!-- 思考指示器 -->
      <ChatThinking
        v-if="isRunning"
        :cancellable="cancellable"
        :cancelling="cancelling"
        @cancel="$emit('cancel')"
      />
    </div>

    <!-- 滚动回底部按钮 -->
    <ChatScrollButton v-if="!isAtBottom" @click="scrollToBottom" />

    <!-- 交付物条：本会话生成的图表缩略图（chat/方案模式统一集中查看） -->
    <div
      v-if="showArtifacts && artifactImages.length"
      class="px-4 sm:px-8 pb-2 shrink-0 bg-background"
    >
      <div class="flex items-center gap-2 overflow-x-auto py-1.5">
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/60 shrink-0"
        >
          交付物 {{ artifactImages.length }}
        </span>
        <a
          v-for="(src, i) in artifactImages"
          :key="`${src}-${i}`"
          :href="src"
          target="_blank"
          rel="noopener"
          class="shrink-0"
          :title="`图表 ${i + 1}（新窗口打开）`"
        >
          <img
            :src="src"
            class="h-12 w-16 object-cover rounded border border-border hover:border-primary/50 transition-colors"
            loading="lazy"
          />
        </a>
      </div>
    </div>

    <!-- 输入区域 -->
    <ChatInput
      :is-running="isRunning"
      :input-placeholder="inputPlaceholder"
      :messages-count="messages.length"
      :prefill="prefillText"
      @send="(text, files) => $emit('send', text, files)"
    />
  </div>
</template>

<script setup lang="ts">
import type { ChatFileRef } from "@/apis/chatApi";
import Bubble from "@/components/Bubble.vue";
import ChatInput from "@/components/chat/ChatInput.vue";
import ChatScrollButton from "@/components/chat/ChatScrollButton.vue";
import ChatThinking from "@/components/chat/ChatThinking.vue";
import ChatToolbar from "@/components/chat/ChatToolbar.vue";
import { useTaskStore } from "@/stores/task";
import type { Message } from "@/types/response";
import { collectImageUrls } from "@/utils/toolOutput";
import { useVirtualizer } from "@tanstack/vue-virtual";
import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  provide,
  ref,
  watch,
} from "vue";

const props = withDefaults(
  defineProps<{
    messages: Message[];
    isRunning?: boolean;
    emptyText?: string;
    emptySubtext?: string;
    inputPlaceholder?: string;
    prefillText?: string;
    sessionTitle?: string;
    showToolbar?: boolean;
    cancellable?: boolean;
    cancelling?: boolean;
    /** 空状态快捷提问(点击走 send 事件)。默认 [] → 不渲染,chat/solution/practice 页不受影响 */
    quickActions?: { label: string; text: string }[];
    /** 折叠气泡内工具卡片产出的图表（方案模式：图表在论文正文还会出现一次） */
    foldToolImages?: boolean;
    /** 底部交付物缩略图条。方案模式关掉：右栏已有同一批图表的缩略图网格 */
    showArtifacts?: boolean;
  }>(),
  {
    isRunning: false,
    emptyText: "开始对话",
    emptySubtext: "在下方输入你的问题",
    inputPlaceholder: "输入消息...",
    prefillText: "",
    sessionTitle: "",
    showToolbar: true,
    cancellable: false,
    cancelling: false,
    quickActions: () => [],
    foldToolImages: false,
    showArtifacts: true,
  },
);

const emit = defineEmits<{
  send: [text: string, files?: ChatFileRef[]];
  cancel: [];
  clear: [];
  "new-session": [];
  openPaper: [];
  retry: [];
}>();

// 提供给 ClarifyCard 注入的发送函数，让用户选择后可以直接发送消息
provide("chatSendHandler", (text: string) => emit("send", text));

const taskStore = useTaskStore();

const isConnecting = computed(
  () =>
    taskStore.wsStatus === "connecting" ||
    taskStore.wsStatus === "reconnecting",
);

const scrollRef = ref<HTMLElement | null>(null);
const isAtBottom = ref(true);

// 交付物：本会话所有工具卡片产出的图表 URL（去重，最近 12 张）
const artifactImages = computed<string[]>(() => {
  const urls: string[] = [];
  for (const m of props.messages) {
    if (m.msg_type !== "tool") continue;
    for (const u of collectImageUrls(m.output)) {
      if (!urls.includes(u)) urls.push(u);
    }
  }
  return urls.slice(-12);
});

// ── 虚拟滚动 ──
const virtualizer = useVirtualizer(
  computed(() => ({
    count: props.messages.length,
    getScrollElement: () => scrollRef.value,
    estimateSize: () => 120,
    overscan: 5,
    getItemKey: (index: number) => props.messages[index]?.id ?? `msg-${index}`,
  })),
);

/** 动态测量消息高度 */
function measureElement(el: HTMLElement | null) {
  virtualizer.value.measureElement(el);
}

/** 滚动到底部（虚拟滚动） */
function scrollToBottom() {
  virtualizer.value.scrollToIndex(props.messages.length - 1, {
    align: "end",
    behavior: "smooth",
  });
}

/** 检测是否在底部 */
function checkAtBottom() {
  const v = virtualizer.value;
  if (!v || !scrollRef.value) return;
  const { scrollTop, scrollHeight, clientHeight } = scrollRef.value;
  isAtBottom.value = scrollHeight - scrollTop - clientHeight < 150;
}

/** 新消息到达时自动滚动 */
watch(
  () => props.messages.length,
  () => {
    if (isAtBottom.value && props.messages.length > 0) {
      nextTick(() => {
        virtualizer.value.scrollToIndex(props.messages.length - 1, {
          align: "end",
        });
      });
    }
  },
);

onMounted(() => {
  scrollRef.value?.addEventListener("scroll", checkAtBottom, { passive: true });
});

onUnmounted(() => {
  scrollRef.value?.removeEventListener("scroll", checkAtBottom);
});
</script>
