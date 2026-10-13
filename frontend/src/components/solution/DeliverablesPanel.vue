<script setup lang="ts">
import {
  Archive,
  Download,
  FileDown,
  FileSpreadsheet,
  FileText,
  Package,
  Paperclip,
  RefreshCw,
  Table,
} from "lucide-vue-next";
/**
 * 交付物面板 —— 方案模式右栏的「图表 / 数据 / 附件 / 报告 / 导出」dock。
 *
 * 为什么单独成组件：这段逻辑原先内嵌在 solution/index.vue（750+ 行的页面）里，
 * 既没法单测、也看不清分组规则。抽出来后输入只有 `files` + `paperMarkdown`，
 * 分组与「正文/过程」标注可以直接在 jsdom 里断言。
 *
 * 图表的「正文 / 过程」标注为什么重要：一个任务可能对同一张图跑过多轮
 * （内容 hash 不同 → 两份文件都留在文件区），平铺会让人分不清哪张真正进了论文。
 */
import { computed } from "vue";

/** 任务文件区的一条记录（与后端 TaskArtifact 对齐） */
export interface TaskFile {
  type: string; // "uploaded" | "figure" | "xlsx" | "csv" | "html" | "zip" | ...
  name: string;
  url: string;
  size?: number;
}

const props = withDefaults(
  defineProps<{
    files: TaskFile[];
    /** 论文正文 Markdown：用于判断图表是否真被正文引用 */
    paperMarkdown?: string;
    /** 任务是否已完成（完成后才提供文档导出） */
    completed?: boolean;
  }>(),
  { paperMarkdown: "", completed: false },
);

const emit = defineEmits<{
  preview: [url: string];
  refresh: [];
  export: [format: "md" | "docx" | "xlsx" | "csv"];
  package: [];
}>();

const IMAGE_SUFFIX_RE = /\.(png|jpg|jpeg|gif|webp)$/i;

function isFigure(f: TaskFile) {
  return f.type === "figure" || IMAGE_SUFFIX_RE.test(f.name);
}
function isSheet(name: string) {
  return name.endsWith(".xlsx") || name.endsWith(".xls");
}
function isHtmlOrZip(name: string) {
  return name.endsWith(".html") || name.endsWith(".zip");
}

/** 图表 + 是否被正文引用 */
const figureItems = computed(() =>
  props.files.filter(isFigure).map((f) => ({
    ...f,
    referenced: !!props.paperMarkdown && props.paperMarkdown.includes(f.url),
  })),
);
const referencedFigureCount = computed(
  () => figureItems.value.filter((f) => f.referenced).length,
);

/** 数据/结果文件（表格、CSV 等） */
const dataFiles = computed(() =>
  props.files.filter(
    (f) => !isFigure(f) && f.type !== "uploaded" && !isHtmlOrZip(f.name),
  ),
);
/** 上传附件（题目 PDF / 数据表），与生成物分开列，避免与结果文件混淆 */
const uploadFiles = computed(() =>
  props.files.filter((f) => f.type === "uploaded"),
);
/** 网页报告与结果包 */
const reportFiles = computed(() =>
  props.files.filter((f) => !isFigure(f) && isHtmlOrZip(f.name)),
);

const hasXlsxFile = computed(() =>
  dataFiles.value.some((f) => isSheet(f.name)),
);
const hasCsvFile = computed(() =>
  dataFiles.value.some((f) => f.name.endsWith(".csv")),
);

function formatSize(bytes?: number) {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
</script>

<template>
  <section class="mt-4" data-testid="deliverables">
    <div class="mb-1 flex items-center gap-1.5">
      <p class="flex items-center gap-1.5 text-xs font-semibold text-foreground">
        <Package class="h-3.5 w-3.5 text-primary" />
        交付物
      </p>
      <span v-if="files.length" class="font-mono text-[10px] text-muted-foreground/70">
        {{ files.length }} 个文件
      </span>
      <button
        class="ml-auto text-muted-foreground hover:text-foreground transition-colors"
        title="重新拉取文件列表"
        @click="emit('refresh')"
      >
        <RefreshCw class="h-3 w-3" />
      </button>
    </div>

    <!-- 图表组：缩略图网格，点击放大预览；「正文」= 论文真的引用了这张图 -->
    <template v-if="figureItems.length">
      <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/60 mt-3 mb-1.5">
        图表 {{ figureItems.length }}
        <span v-if="referencedFigureCount" class="normal-case tracking-normal">
          · 正文引用 {{ referencedFigureCount }}
        </span>
      </p>
      <div class="grid grid-cols-3 gap-1.5" data-testid="figures">
        <button
          v-for="f in figureItems"
          :key="f.url"
          class="group relative aspect-square overflow-hidden rounded-md border transition-colors"
          :class="f.referenced
            ? 'border-border hover:border-primary/50'
            : 'border-dashed border-border/70 opacity-70 hover:border-primary/40 hover:opacity-100'"
          :title="f.referenced ? `${f.name}（已进论文正文）` : `${f.name}（过程图，未进正文）`"
          @click="emit('preview', f.url)"
        >
          <img :src="f.url" class="h-full w-full object-cover" loading="lazy" />
          <span
            class="absolute left-1 top-1 rounded px-1 py-px text-[9px] leading-3"
            :class="f.referenced ? 'bg-emerald-500/90 text-white' : 'bg-black/55 text-white/80'"
          >
            {{ f.referenced ? "正文" : "过程" }}
          </span>
        </button>
      </div>
    </template>

    <!-- 数据文件组 -->
    <template v-if="dataFiles.length">
      <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/60 mt-3 mb-1.5">
        数据文件 {{ dataFiles.length }}
      </p>
      <div class="space-y-1">
        <div
          v-for="f in dataFiles"
          :key="f.url"
          class="flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs hover:bg-accent transition-colors"
        >
          <FileSpreadsheet v-if="isSheet(f.name)" class="h-4 w-4 text-green-500 shrink-0" />
          <Table v-else-if="f.name.endsWith('.csv')" class="h-4 w-4 text-blue-500 shrink-0" />
          <Paperclip v-else class="h-4 w-4 text-muted-foreground shrink-0" />
          <span class="flex-1 truncate" :title="f.name">{{ f.name }}</span>
          <span v-if="f.size" class="shrink-0 font-mono text-[10px] text-muted-foreground/60">
            {{ formatSize(f.size) }}
          </span>
          <a
            :href="f.url"
            :download="f.name"
            class="text-muted-foreground hover:text-foreground shrink-0"
            title="下载"
          >
            <Download class="h-3.5 w-3.5" />
          </a>
        </div>
      </div>
    </template>

    <!-- 网页报告与结果包组 -->
    <template v-if="reportFiles.length">
      <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/60 mt-3 mb-1.5">
        报告与结果包 {{ reportFiles.length }}
      </p>
      <div class="space-y-1">
        <div
          v-for="f in reportFiles"
          :key="f.url"
          class="flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs hover:bg-accent transition-colors"
        >
          <FileText v-if="f.name.endsWith('.html')" class="h-4 w-4 text-orange-500 shrink-0" />
          <Archive v-else class="h-4 w-4 text-purple-500 shrink-0" />
          <span class="flex-1 truncate" :title="f.name">{{ f.name }}</span>
          <span v-if="f.size" class="shrink-0 font-mono text-[10px] text-muted-foreground/60">
            {{ formatSize(f.size) }}
          </span>
          <a
            :href="f.url"
            :download="f.name"
            class="text-muted-foreground hover:text-foreground shrink-0"
            title="下载"
          >
            <Download class="h-3.5 w-3.5" />
          </a>
        </div>
      </div>
    </template>

    <!-- 上传附件组 -->
    <template v-if="uploadFiles.length">
      <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/60 mt-3 mb-1.5">
        上传附件 {{ uploadFiles.length }}
      </p>
      <div class="space-y-1">
        <a
          v-for="f in uploadFiles"
          :key="f.url"
          :href="f.url"
          :download="f.name"
          class="flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs hover:bg-accent transition-colors"
          :title="`下载 ${f.name}`"
        >
          <Paperclip class="h-4 w-4 text-muted-foreground shrink-0" />
          <span class="flex-1 truncate">{{ f.name }}</span>
          <Download class="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </a>
      </div>
    </template>

    <!-- 文档导出组（任务完成后） -->
    <template v-if="completed">
      <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/60 mt-3 mb-1.5">
        文档导出
      </p>
      <div class="space-y-1.5">
        <button
          class="flex items-center gap-2 w-full rounded-md border px-3 py-2 text-sm hover:bg-accent transition-colors"
          @click="emit('export', 'md')"
        >
          <FileText class="h-4 w-4" /> Markdown (.md)
        </button>
        <button
          class="flex items-center gap-2 w-full rounded-md border px-3 py-2 text-sm hover:bg-accent transition-colors"
          @click="emit('export', 'docx')"
        >
          <FileDown class="h-4 w-4" /> Word (.docx)
        </button>
        <button
          v-if="hasXlsxFile"
          class="flex items-center gap-2 w-full rounded-md border px-3 py-2 text-sm hover:bg-accent transition-colors"
          @click="emit('export', 'xlsx')"
        >
          <FileSpreadsheet class="h-4 w-4" /> Excel (.xlsx)
        </button>
        <button
          v-if="hasCsvFile"
          class="flex items-center gap-2 w-full rounded-md border px-3 py-2 text-sm hover:bg-accent transition-colors"
          @click="emit('export', 'csv')"
        >
          <Table class="h-4 w-4" /> CSV (.csv)
        </button>
        <button
          class="flex items-center gap-2 w-full rounded-md border px-3 py-2 text-sm hover:bg-accent transition-colors"
          @click="emit('package')"
        >
          <Archive class="h-4 w-4" /> 完整结果包 (.zip)
        </button>
      </div>
    </template>

    <!-- 空状态 -->
    <div v-if="files.length === 0" class="mt-2 text-[11px] text-muted-foreground">
      {{ completed ? "本任务没有生成文件" : "上传的题目/数据与生成的图表将显示在这里" }}
    </div>
  </section>
</template>
