<template>
  <div ref="docRoot" class="learning-doc relative h-full overflow-y-auto" @scroll="onScroll" @mousedown="onDocMouseDown" @contextmenu.prevent>
    <div class="sticky top-0 left-0 right-0 h-0.5 bg-border z-10">
      <div class="h-full bg-primary transition-all duration-150" :style="{ width: progressPercent + '%' }" />
    </div>
    <div class="px-8 py-6 max-w-2xl mx-auto">
      <div ref="contentRef" class="prose prose-sm prose-gray dark:prose-invert max-w-none" v-html="renderedHtml" />
      <!-- 文档末尾扩展区(如单元自测块) -->
      <slot />
    </div>
    <div class="h-64" />

    <!-- 仿浏览器蓝色选区覆盖层 -->
    <Teleport to="body">
      <div v-if="fakeSel.visible" class="fixed inset-0 pointer-events-none z-40">
        <div v-for="(r, i) in fakeSel.rects" :key="i"
          class="absolute" style="background: rgba(0,102,204,0.25);"
          :style="{ left: r.left + 'px', top: r.top + window.scrollY + 'px', width: r.width + 'px', height: r.height + 'px' }" />
      </div>
    </Teleport>

    <!-- Mini Toolbar -->
    <Teleport to="body">
      <div v-if="toolbar.visible" class="fixed z-50 flex items-center gap-0.5 rounded-md border border-border bg-card shadow-lg px-1.5 py-1.5" :style="{ left: toolbar.x + 'px', top: toolbar.y + 'px' }">
        <button class="flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-accent" @mousedown.stop.prevent="doAskAI">
          <MessageCircleQuestion class="h-3.5 w-3.5" />问AI
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import DOMPurify from "dompurify";
import { MessageCircleQuestion } from "lucide-vue-next";
import { marked } from "marked";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";

const props = defineProps<{
  markdown: string;
  unitId: string;
  onAskAI?: (text: string, section: string) => void;
}>();

const emit = defineEmits<{
  headingsChange: [headings: { id: string; text: string; level: number }[]];
  scrollSection: [id: string];
}>();

const docRoot = ref<HTMLElement>();
const contentRef = ref<HTMLElement>();
const progressPercent = ref(0);

const renderedHtml = computed(() => {
  if (!props.markdown)
    return "<p class='text-muted-foreground'>暂无学习资料</p>";
  const raw = marked.parse(props.markdown) as string;
  // 按标题/引用文本关键词打白名单 class(仅注入 class,再 sanitize 兜底)
  const div = document.createElement("div");
  div.innerHTML = raw;
  for (const h of div.querySelectorAll("h2")) {
    const t = h.textContent || "";
    let cls = "";
    if (/学习目标|本单元|你将|学完/.test(t)) cls = "sec-goal";
    else if (/核心概念|核心知识|概念|关键|要点|知识点/.test(t))
      cls = "sec-concept";
    else if (/公式/.test(t)) cls = "sec-formula";
    else if (/例题|示例|举例|案例/.test(t)) cls = "sec-example";
    else if (/练习|习题|自测|检测|巩固/.test(t)) cls = "sec-practice";
    if (cls) h.className = cls;
  }
  for (const b of div.querySelectorAll("blockquote")) {
    const t = b.textContent || "";
    if (/AI提示|AI 提示|提示|注意|建议|💡/.test(t)) {
      b.className = b.className ? `${b.className} sec-tip` : "sec-tip";
    }
  }
  return DOMPurify.sanitize(div.innerHTML);
});

function extractHeadings() {
  if (!contentRef.value) return;
  const hs = contentRef.value.querySelectorAll("h1, h2, h3");
  const r: { id: string; text: string; level: number }[] = [];
  let n = 0;
  for (const h of hs) {
    h.id = `h-${n++}`;
    r.push({ id: h.id, text: h.textContent || "", level: +h.tagName[1] });
  }
  emit("headingsChange", r);
}
// 首次挂载时 v-html 渲染完成后提取(此前只挂 watch,首访 markdown 不变 → 目录恒空)
onMounted(() => nextTick(extractHeadings));
// 切换单元时 markdown 变化 → 重新提取
watch(renderedHtml, () => nextTick(extractHeadings));

// ── 选区 ────────────────────────────────────────────

const toolbar = ref({ visible: false, x: 0, y: 0 });
const fakeSel = ref<{ visible: boolean; rects: DOMRect[] }>({
  visible: false,
  rects: [],
});
let selectedText = "";
let selectedSection = "";
const window = { scrollY: 0 };

function updateScrollY() {
  window.scrollY = globalThis.scrollY || 0;
}

function onDocMouseDown() {
  setTimeout(() => {
    toolbar.value.visible = false;
    fakeSel.value.visible = false;
  }, 200);
}

function onGlobalMouseUp() {
  updateScrollY();
  const sel = document.getSelection ? document.getSelection() : null;
  if (!sel || sel.isCollapsed) return;
  if (!contentRef.value) return;
  const an = sel.anchorNode;
  const fn = sel.focusNode;
  if (
    !an ||
    !fn ||
    !contentRef.value.contains(an) ||
    !contentRef.value.contains(fn)
  )
    return;
  const t = sel.toString().trim();
  if (t.length < 1) return;

  selectedText = t;
  let n: Node | null = an;
  while (n && n !== contentRef.value) {
    if (n.nodeName?.match(/^H[1-4]$/)) {
      selectedSection = n.textContent || "";
      break;
    }
    n = n.parentElement as Node | null;
  }

  // 保存选区矩形 → 仿蓝色高亮
  const rects: DOMRect[] = [];
  try {
    for (let i = 0; i < sel.rangeCount; i++) {
      const r = sel.getRangeAt(i).getClientRects();
      for (let j = 0; j < r.length; j++) rects.push(r[j].toJSON());
    }
  } catch {}
  fakeSel.value = { visible: true, rects };

  // 用第一个矩形定位 toolbar
  const rc = sel.getRangeAt(0).getBoundingClientRect();
  toolbar.value = {
    visible: true,
    x: Math.max(10, rc.left + rc.width / 2 - 70),
    y: Math.max(10, rc.top - 44),
  };

  // 清浏览器选区 → 蓝高亮由 fakeSel 维持
  sel.removeAllRanges();
}

function doAskAI() {
  if (selectedText && props.onAskAI)
    props.onAskAI(selectedText, selectedSection);
  toolbar.value.visible = false;
  fakeSel.value.visible = false;
}

// ── 滚动 ────────────────────────────────────────────

function onScroll() {
  if (!docRoot.value) return;
  const { scrollTop, scrollHeight, clientHeight } = docRoot.value;
  const p = Math.round((scrollTop / (scrollHeight - clientHeight)) * 100);
  progressPercent.value = Number.isNaN(p) ? 0 : Math.min(100, Math.max(0, p));
  if (!contentRef.value) return;
  let id = "";
  for (const h of contentRef.value.querySelectorAll("h1,h2,h3")) {
    if (h.getBoundingClientRect().top <= 120) id = h.id;
  }
  if (id) emit("scrollSection", id);

  // 滚动时隐藏仿高亮
  fakeSel.value.visible = false;
}
function scrollToHeading(id: string) {
  contentRef.value
    ?.querySelector(`#${id}`)
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}
defineExpose({ scrollToHeading });

onMounted(() => {
  document.addEventListener("mouseup", onGlobalMouseUp);
  globalThis.addEventListener("scroll", updateScrollY, true);
});
onBeforeUnmount(() => {
  document.removeEventListener("mouseup", onGlobalMouseUp);
  globalThis.removeEventListener("scroll", updateScrollY, true);
});
</script>

<style scoped>
.prose :deep(h1), .prose :deep(h2), .prose :deep(h3) { scroll-margin-top: 80px; }
.prose :deep(pre) { background: #1e1e2e; color: #cdd6f4; border-radius: 0.5rem; padding: 1rem; overflow-x: auto; }
.prose :deep(pre code) { color: #cdd6f4; font-size: 0.875em; }
.prose :deep(code) { font-size: 0.875em; }
.prose :deep(.katex) { font-size: 1.1em; }

/* ── 内容视觉层级: h2 主色左边条,按章节类型分色 ── */
.prose :deep(h2) {
  position: relative;
  padding-left: 0.875rem;
  margin-top: 2.25em;
}
.prose :deep(h2)::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.12em;
  bottom: 0.12em;
  width: 3px;
  border-radius: 999px;
  background: hsl(var(--primary));
}
.prose :deep(h2.sec-goal)::before { background: hsl(150 60% 40%); }
.prose :deep(h2.sec-concept)::before { background: hsl(var(--primary)); }
.prose :deep(h2.sec-example)::before { background: hsl(35 85% 50%); }
.prose :deep(h2.sec-practice)::before { background: hsl(270 50% 55%); }

/* 公式章节: 居中 + 上下发丝线,更像视觉分隔 */
.prose :deep(h2.sec-formula) {
  text-align: center;
  border-top: 1px solid hsl(var(--border));
  border-bottom: 1px solid hsl(var(--border));
  padding: 0.6em 0;
  margin-top: 2.5em;
  margin-bottom: 1.5em;
}
.prose :deep(h2.sec-formula)::before { display: none; }

/* h3: 菱形点缀,层级收窄 */
.prose :deep(h3)::before {
  content: "◆";
  font-size: 0.62em;
  margin-right: 0.5em;
  color: hsl(var(--primary));
  vertical-align: 0.08em;
}

/* AI 提示 callout */
.prose :deep(blockquote.sec-tip) {
  background: hsl(var(--accent) / 0.4);
  border-left: 3px solid hsl(var(--primary));
  border-radius: 0 0.5rem 0.5rem 0;
  padding: 0.75rem 1rem;
  font-style: normal;
}
.prose :deep(blockquote.sec-tip) p:first-child::before { content: "提示 · "; font-weight: 600; color: hsl(var(--primary)); }

/* 表格: 斑马表头 */
.prose :deep(table) { font-size: 0.875em; }
.prose :deep(thead) { background: hsl(var(--muted)); }
.prose :deep(thead th) { text-align: left; }
</style>
