<script setup lang="ts">
import { getAgentIdentity } from "@/components/agent/AgentIdentity";
import ThinkingBlock from "@/components/agent/ThinkingBlock.vue";
import BubbleTool from "@/components/bubble/BubbleTool.vue";
import PaperCard from "@/components/paper/PaperCard.vue";
import { useTypewriter } from "@/composables/useTypewriter";
import { AgentType } from "@/types/enum";
import type { AgentMessage, AgentSegment, Message } from "@/types/response";
import { renderMarkdown } from "@/utils/markdown";
import { BookOpen, Clipboard, Printer, RotateCcw } from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import BubbleAvatar from "./BubbleAvatar.vue";

const props = withDefaults(
  defineProps<{
    message: Message;
    isLast?: boolean;
    /** chat 模式：本气泡内联的工具卡片（dsh 式"工具嵌在输出中"） */
    attachedTools?: Message[];
    /** chat 模式：文本与工具按事件顺序交错的片段流（存在时优先按序渲染） */
    segments?: AgentSegment[];
    /** 折叠内联工具卡片里的图表（方案模式；见 RunCodeRenderer.foldImages） */
    foldToolImages?: boolean;
  }>(),
  {
    isLast: false,
    attachedTools: () => [],
    segments: () => [],
    foldToolImages: false,
  },
);

const emit = defineEmits<{
  openPaper: [];
  retry: [];
}>();

const content = computed(() => props.message.content ?? "");

// 打字机仅用于「非流式的一次性外部消息」
const enableTypewriter = computed(
  () => props.isLast && !("streaming" in props.message),
);
const rawText = ref(content.value);
const { displayText, isTyping, skip } = useTypewriter(
  rawText,
  12,
  enableTypewriter,
);

watch(
  content,
  (val) => {
    rawText.value = val;
  },
  { immediate: true },
);

onMounted(() => {
  if (!content.value) return;
  displayText.value = content.value;
  isTyping.value = false;
});

const identity = computed(() =>
  getAgentIdentity((props.message as AgentMessage).agent_type),
);

const agentLabel = computed(() => {
  const agentType = (props.message as AgentMessage).agent_type;
  if (!agentType) return "";
  return identity.value?.label ?? "";
});

const isFinalPaper = computed(
  () =>
    typeof props.message.id === "string" &&
    props.message.id.startsWith("final-"),
);
const copied = ref(false);

async function copyMarkdown() {
  try {
    await navigator.clipboard.writeText(content.value);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 1500);
  } catch {
    /* ignore */
  }
}

function exportPdf() {
  import("@/utils/exportPaper").then(({ exportPaperAsPDF }) => {
    exportPaperAsPDF({ title: "数学建模论文", markdown: content.value });
  });
}

const renderedContent = computed(() => {
  const text = enableTypewriter.value ? displayText.value : content.value;
  if (!text) return "";
  return renderMarkdown(text);
});

// 片段流渲染：toolId → 工具消息查表（BubbleTool 直接拿消息对象）
const toolMap = computed(
  () => new Map((props.attachedTools ?? []).map((t) => [t.id, t])),
);

function segHtml(seg: AgentSegment): string {
  return seg.kind === "text" && seg.text ? renderMarkdown(seg.text) : "";
}

const timestamp = computed(() => {
  if (!props.message.created_at) return "";
  return new Date(props.message.created_at).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
});
</script>

<template>
  <div class="flex gap-3 w-full my-2 animate-in fade-in slide-in-from-bottom-2">
    <div class="flex shrink-0 flex-col items-center self-start pt-0.5">
      <BubbleAvatar :message="message" />
    </div>
    <div class="flex-1 min-w-0">
      <div class="flex flex-col items-start">
        <div class="max-w-[85%] rounded-md rounded-bl-sm border border-border bg-background text-foreground px-4 py-3 text-sm leading-relaxed">
          <!-- Agent 标签 -->
          <div v-if="agentLabel" class="mb-1.5 flex items-center gap-1.5">
            <span class="font-mono text-[10px] uppercase tracking-wider" :class="identity?.textColor ?? 'text-muted-foreground'">
              [{{ agentLabel }}]
            </span>
            <!-- 流式活跃指示器 -->
            <span v-if="message.streaming" class="h-1.5 w-1.5 rounded-full animate-pulse" :class="identity?.color ?? 'bg-foreground'" />
          </div>

          <!-- 思考过程（可折叠） -->
          <ThinkingBlock
            v-if="(message as AgentMessage).thinking"
            :thinking="(message as AgentMessage).thinking || ''"
            :streaming="message.streaming"
          />

          <!-- 内容 / 打字机 / 思考点 -->
          <!-- 片段流（chat 模式）：文本与工具按事件顺序交错渲染 -->
          <div v-if="segments && segments.length" class="w-full space-y-2">
            <template v-for="(seg, i) in segments" :key="i">
              <div
                v-if="seg.kind === 'text' && seg.text"
                class="prose prose-sm dark:prose-invert max-w-none break-words"
                v-html="segHtml(seg)"
              />
              <BubbleTool
                v-else-if="seg.kind === 'tool' && toolMap.get(seg.toolId)"
                :message="toolMap.get(seg.toolId)!"
                :fold-images="foldToolImages"
                inline
              />
            </template>
          </div>

          <!-- 论文消息：显示 PaperCard 代替全文渲染 -->
          <PaperCard
            v-else-if="isFinalPaper && content"
            :markdown="content"
            @open="emit('openPaper')"
          />
          <div
            v-else-if="content"
            class="prose prose-sm dark:prose-invert max-w-none break-words"
            :class="{ 'cursor-pointer': isTyping }"
            v-html="renderedContent"
            @click="isTyping && skip()"
          />
          <div v-else class="flex items-center gap-1.5 py-1">
            <span class="h-1.5 w-1.5 rounded-full bg-current animate-bounce" style="animation-delay: 0ms" />
            <span class="h-1.5 w-1.5 rounded-full bg-current animate-bounce" style="animation-delay: 150ms" />
            <span class="h-1.5 w-1.5 rounded-full bg-current animate-bounce" style="animation-delay: 300ms" />
          </div>

          <!-- 出错重试（onError 置位；只出现在最后一条） -->
          <div
            v-if="(message as AgentMessage).error && isLast"
            class="mt-2 flex items-center gap-2 border-t border-border pt-2"
          >
            <button
              class="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-xs hover:bg-accent hover:text-foreground transition-colors"
              @click="emit('retry')"
            >
              <RotateCcw class="h-3 w-3" />
              <span>重试</span>
            </button>
            <span class="text-[10px] text-muted-foreground">重新生成（不会重复发送问题）</span>
          </div>

          <!-- 论文操作 -->
          <div v-if="isFinalPaper" class="mt-2 flex items-center gap-2 border-t border-border pt-2">
            <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">论文操作</span>
            <button
              class="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-xs hover:bg-accent hover:text-foreground transition-colors"
              title="在新窗口中打开论文并调出打印对话框，可保存为 PDF"
              @click="exportPdf"
            >
              <Printer class="h-3 w-3" />
              <span>导出 PDF</span>
            </button>
            <button
              class="inline-flex h-7 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-xs hover:bg-accent hover:text-foreground transition-colors"
              title="复制论文 Markdown 源（含 LaTeX 公式）"
              @click="copyMarkdown"
            >
              <Clipboard class="h-3 w-3" />
              <span>{{ copied ? "已复制" : "复制 Markdown" }}</span>
            </button>
          </div>
        </div>
        <span v-if="timestamp" class="font-mono text-[10px] text-muted-foreground/50 mt-0.5">{{ timestamp }}</span>
      </div>
    </div>
  </div>
</template>
