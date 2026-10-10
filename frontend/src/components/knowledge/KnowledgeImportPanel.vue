<template>
  <div class="rounded-lg border border-border bg-background p-6">
    <!-- 导入引导提示：手稿边注风格 -->
    <div class="border-l-2 border-foreground/50 pl-4 mb-6">
      <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">
        § 导入说明 · {{ impTypeLabel }}
      </p>
      <p class="text-xs leading-relaxed text-foreground/75">
        <template v-if="impType === 'problem'">上传竞赛真题原文。系统会提取年份、赛事、题号，作为后续论文关联的唯一标识。建议<strong class="font-medium text-foreground">先导入题目</strong>，再导入对应论文。</template>
        <template v-else-if="impType === 'paper'">
          <template v-if="lastProblemRef">上传后将<strong class="font-medium text-foreground">自动关联到 {{ lastProblemRef }}</strong>，无需额外操作。</template>
          <template v-else>先导入题目，再从此处追加论文，系统会自动关联。或直接上传，系统根据<strong class="font-medium text-foreground">年份+赛事+题号</strong>自动匹配。</template>
        </template>
        <template v-else-if="impType === 'method'">上传数学建模方法的描述文本。系统会提取原理、适用条件、代码示例等信息。</template>
        <template v-else>上传分析框架描述。系统会提取引导问题、决策树和检查清单。</template>
      </p>
    </div>
    <div class="flex items-center gap-x-5 gap-y-2 mb-5 flex-wrap">
      <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">类型</span>
      <button v-for="o in impTypes" :key="o.value"
        class="font-mono text-[10px] uppercase tracking-wider transition-colors"
        :class="impType === o.value ? 'text-primary' : 'text-muted-foreground/60 hover:text-foreground'"
        @click="impType = o.value">{{ o.label }}</button>
    </div>

    <!-- File drop zone -->
    <div class="relative rounded-md border border-dashed border-border p-6 text-center cursor-pointer transition-colors"
      :class="dragOver ? 'border-primary bg-primary/5' : impFiles ? 'border-primary/50 bg-primary/5' : 'hover:border-muted-foreground/50'"
      @click="triggerFileInput" @dragover.prevent="dragOver = true" @dragleave.prevent="dragOver = false" @drop.prevent="onDrop">
      <input ref="fileRef" type="file" multiple accept=".txt,.md,.pdf,.doc,.docx,.tex,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.gif,.webp,.bmp" class="hidden" @change="onFileSel" />
      <template v-if="impFiles.length > 0">
        <div class="space-y-1.5 text-left w-full">
          <div v-for="(f, i) in impFiles" :key="i" class="flex items-center gap-2 text-sm rounded-md bg-muted/30 px-3 py-1.5">
            <FileText class="h-4 w-4 shrink-0 text-primary" />
            <span class="font-medium truncate flex-1 min-w-0">{{ f.name }}</span>
            <span class="font-mono text-[10px] text-muted-foreground shrink-0">{{ fmtSize(f.size) }}</span>
            <button class="rounded-md p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive shrink-0" @click.stop="removeFile(i)"><X class="h-3 w-3" /></button>
          </div>
        </div>
        <p class="font-mono text-[10px] text-muted-foreground/70 mt-2">{{ impFiles.length }} 个文件，可在下方补充文本后一起提取</p>
      </template>
      <template v-else>
        <FileUp class="h-8 w-8 mx-auto text-muted-foreground/40 mb-2" />
        <p class="text-sm text-muted-foreground">拖拽文件到此处，或<span class="text-primary">点击选择</span>（支持多选）</p>
        <p class="font-mono text-[10px] text-muted-foreground/60 mt-1">Excel / CSV / PDF / DOCX / TXT / 图片 / GIF</p>
      </template>
    </div>

    <label class="block font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-2 mt-5">{{ impFiles.length > 0 ? '补充文本(可选)' : '粘贴原始文本' }}</label>
    <textarea v-model="impText" rows="8" :placeholder="impPlaceholder"
      class="w-full resize-y rounded-md border border-border bg-background px-4 py-3 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
    <div class="flex items-center gap-2 mt-3 flex-wrap">
      <input v-model="impName" type="text" placeholder="名称(可选)" class="flex-1 min-w-0 rounded-md border border-border bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      <button class="flex items-center whitespace-nowrap rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background hover:bg-foreground/90 disabled:opacity-50 transition-transform hover:scale-[0.98] active:scale-[0.97]"
        :disabled="(!impText.trim() && impFiles.length === 0) || extracting" @click="doExtract">
        <Loader2 v-if="extracting" class="h-4 w-4 mr-1.5 animate-spin" /><Sparkles v-else class="h-4 w-4 mr-1.5" />{{ extracting ? '提取中' : 'LLM 提取并预览' }}
      </button>
    </div>
    <div v-if="extractError" class="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{{ extractError }}</div>
    <div v-if="savedNotice" class="mt-4 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-400 flex items-center gap-3 flex-wrap">
      <span class="flex items-center gap-1.5"><CheckCircle2 class="h-4 w-4 shrink-0" />{{ savedNotice }}</span>
      <button class="ml-auto rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent transition-colors" @click="emit('goto-manage', impType)">去管理知识查看</button>
    </div>
    <div v-if="extractPreview" class="mt-4">
      <p class="font-mono text-[10px] uppercase tracking-wider text-primary mb-2">提取完成</p>
      <pre class="rounded-md bg-zinc-950 p-4 font-mono text-xs text-zinc-300 overflow-auto max-h-96">{{ extractPreview }}</pre>
      <div class="flex gap-2 mt-3">
        <button class="flex items-center rounded-md bg-foreground px-5 py-2 text-sm font-medium text-background hover:bg-foreground/90 disabled:opacity-50 transition-transform hover:scale-[0.98] active:scale-[0.97]"
          :disabled="saving" @click="doSaveExtract"><Check v-if="!saving" class="h-4 w-4 mr-1" /><Loader2 v-else class="h-4 w-4 mr-1 animate-spin" />{{ saving ? '保存中' : '保存到知识库' }}</button>
        <button class="flex items-center rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors" @click="extractPreview = ''; extractError = ''"><RotateCcw class="h-4 w-4 mr-1" />重新提取</button>
      </div>
    </div>

    <!-- 论文上传区: 始终可见 -->
    <div class="mt-8 pt-6 border-t-2 border-border">
      <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-1">§ 论文上传</p>
      <p class="font-display text-lg font-medium mb-1">上传对应论文</p>
      <p v-if="lastProblemRef" class="text-xs text-muted-foreground mb-5">关联到题目 <span class="font-mono text-primary">{{ lastProblemRef }}</span></p>
      <p v-else class="text-xs text-muted-foreground mb-5">先导入题目后论文将自动关联，也可独立上传</p>

      <!-- Paper file drop zone -->
      <div class="relative rounded-md border border-dashed border-border p-5 text-center cursor-pointer transition-colors"
        :class="paperDragOver ? 'border-primary bg-primary/5' : paperFiles.length > 0 ? 'border-primary/50 bg-primary/5' : 'hover:border-muted-foreground/50'"
        @click="paperTriggerFile" @dragover.prevent="paperDragOver = true" @dragleave.prevent="paperDragOver = false" @drop.prevent="paperOnDrop">
        <input ref="paperFileRef" type="file" multiple accept=".txt,.md,.pdf,.doc,.docx,.tex" class="hidden" @change="paperOnFileSel" />
        <template v-if="paperFiles.length > 0">
          <div class="space-y-1 text-left w-full">
            <div v-for="(f, i) in paperFiles" :key="i" class="flex items-center gap-2 text-sm rounded-md bg-muted/30 px-3 py-1.5">
              <FileText class="h-4 w-4 shrink-0 text-primary" />
              <span class="font-medium truncate flex-1 min-w-0">{{ f.name }}</span>
              <span class="font-mono text-[10px] text-muted-foreground shrink-0">{{ fmtSize(f.size) }}</span>
              <button class="rounded-md p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive shrink-0" @click.stop="paperRemoveFile(i)"><X class="h-3 w-3" /></button>
            </div>
          </div>
          <p class="font-mono text-[10px] text-muted-foreground/70 mt-2">{{ paperFiles.length }} 个文件</p>
        </template>
        <template v-else>
          <FileUp class="h-7 w-7 mx-auto text-muted-foreground/40 mb-1.5" />
          <p class="text-sm text-muted-foreground">拖拽论文文件，或<span class="text-primary">点击选择</span></p>
          <p class="font-mono text-[10px] text-muted-foreground/60 mt-1">PDF / DOCX / TXT / MD / TEX</p>
        </template>
      </div>

      <label class="block font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-2 mt-4">补充文本(可选)</label>
      <textarea v-model="paperText" rows="4" placeholder="粘贴论文描述..."
        class="w-full resize-y rounded-md border border-border bg-background px-4 py-3 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
      <div class="flex items-center gap-2 mt-3 flex-wrap">
        <input v-model="paperName" type="text" placeholder="论文名称(可选)" class="flex-1 min-w-0 rounded-md border border-border bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <button class="flex items-center whitespace-nowrap rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background hover:bg-foreground/90 disabled:opacity-50 transition-transform hover:scale-[0.98] active:scale-[0.97]"
          :disabled="(!paperText.trim() && paperFiles.length === 0) || paperExtracting" @click="paperDoExtract">
          <Loader2 v-if="paperExtracting" class="h-4 w-4 mr-1.5 animate-spin" /><Sparkles v-else class="h-4 w-4 mr-1.5" />{{ paperExtracting ? '提取中' : 'LLM 提取并预览' }}
        </button>
      </div>
      <div v-if="paperError" class="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{{ paperError }}</div>
      <div v-if="paperPreview" class="mt-4">
        <p class="font-mono text-[10px] uppercase tracking-wider text-primary mb-2">提取完成</p>
        <pre class="rounded-md bg-zinc-950 p-4 font-mono text-xs text-zinc-300 overflow-auto max-h-96">{{ paperPreview }}</pre>
        <div class="flex gap-2 mt-3">
          <button class="flex items-center rounded-md bg-foreground px-5 py-2 text-sm font-medium text-background hover:bg-foreground/90 disabled:opacity-50 transition-transform hover:scale-[0.98] active:scale-[0.97]"
            :disabled="paperSaving" @click="paperDoSave"><Check v-if="!paperSaving" class="h-4 w-4 mr-1" /><Loader2 v-else class="h-4 w-4 mr-1 animate-spin" />{{ paperSaving ? '保存中' : '保存到知识库' }}</button>
          <button class="flex items-center rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors" @click="paperPreview = ''; paperError = ''"><RotateCcw class="h-4 w-4 mr-1" />重新提取</button>
        </div>
      </div>

      <button v-if="lastProblemRef" class="mt-4 flex items-center gap-1 font-mono text-[10px] text-muted-foreground/50 hover:text-muted-foreground transition-colors" @click="lastProblemRef = ''">清除关联</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getExtractionJob, uploadKnowledge } from "@/apis/knowledgeApi";
import {
  Check,
  CheckCircle2,
  FileText,
  FileUp,
  Loader2,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-vue-next";
import { computed, ref } from "vue";

const emit = defineEmits<{
  (e: "refresh-stats"): void;
  (e: "goto-manage", subType: string): void;
}>();

// ── Tab 3: Import ───────────────────────────────────────────────
// 题目/方法/模板上传
const impType = ref("problem");
const impText = ref("");
const impName = ref("");
const impFiles = ref<File[]>([]);
const dragOver = ref(false);
const fileRef = ref<HTMLInputElement | null>(null);
const extracting = ref(false);
const saving = ref(false);
const extractPreview = ref("");
const extractError = ref("");
const extractedEntryId = ref("");
const savedNotice = ref("");
const impTypes = [
  { label: "竞赛真题", value: "problem" },
  { label: "方法卡片", value: "method" },
  { label: "框架模板", value: "template" },
];

// 论文上传（独立状态，关联到已导入的题目）
const paperText = ref("");
const paperName = ref("");
const paperFiles = ref<File[]>([]);
const paperDragOver = ref(false);
const paperFileRef = ref<HTMLInputElement | null>(null);
const paperExtracting = ref(false);
const paperSaving = ref(false);
const paperPreview = ref("");
const paperError = ref("");
const paperExtractedEntryId = ref("");
const impTypeLabel = computed(
  () => impTypes.find((o) => o.value === impType.value)?.label ?? "",
);
const impPlaceholder = computed(
  () =>
    ({
      method:
        "粘贴方法描述...\n例如: 粒子群优化算法(PSO)是一种基于群体智能的启发式优化算法...",
      paper: "粘贴论文内容...\n例如: 2024年国赛A题优秀论文...",
      template: "粘贴分析框架描述...\n例如: 第一步: 问题识别...",
      problem: "粘贴竞赛真题...\n例如: 2024年国赛B题...",
    })[impType.value],
);

function triggerFileInput() {
  fileRef.value?.click();
}
function onFileSel(e: Event) {
  const fl = (e.target as HTMLInputElement).files;
  if (fl) addFiles(Array.from(fl));
}
function onDrop(e: DragEvent) {
  dragOver.value = false;
  if (e.dataTransfer?.files) addFiles(Array.from(e.dataTransfer.files));
}
function addFiles(newFiles: File[]) {
  const valid = newFiles.filter((f) => f.size <= 10 * 1024 * 1024);
  if (valid.length < newFiles.length)
    extractError.value = "部分文件超过 10MB 已跳过";
  impFiles.value = [...impFiles.value, ...valid];
  if (!impName.value && valid.length > 0)
    impName.value = valid[0].name.replace(/\.[^.]+$/, "");
  // Pre-load small text files for preview; binary files handled by backend
  for (const f of valid) {
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (
      ext &&
      ["txt", "md", "tex", "csv"].includes(ext) &&
      f.size < 500 * 1024
    ) {
      const r = new FileReader();
      r.onload = () => {
        if (!impText.value) impText.value = r.result as string;
      };
      r.readAsText(f);
    }
  }
}
function removeFile(i: number) {
  impFiles.value.splice(i, 1);
}
function clearAll() {
  impFiles.value = [];
  impText.value = "";
  if (fileRef.value) fileRef.value.value = "";
}
// 追加论文: 记录最后导入的题目 ID
const lastProblemRef = ref("");
function fmtSize(b: number) {
  if (b < 1024) return `${b}B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)}KB`;
  return `${(b / 1048576).toFixed(1)}MB`;
}

async function doExtract() {
  if (!impText.value.trim() && impFiles.value.length === 0) return;
  extracting.value = true;
  extractError.value = "";
  extractPreview.value = "";
  extractedEntryId.value = "";
  savedNotice.value = "";
  try {
    const uploadParams: {
      text?: string;
      files?: File[];
      kb_type: string;
      name?: string;
      problem_ref?: string;
    } = {
      text: impText.value.trim() || undefined,
      files: impFiles.value.length > 0 ? impFiles.value : undefined,
      kb_type: impType.value,
      name: impName.value,
    };
    if (impType.value === "paper" && lastProblemRef.value) {
      uploadParams.problem_ref = lastProblemRef.value;
    }
    const res = await uploadKnowledge(uploadParams);
    let tries = 0;
    while (tries < 60) {
      await new Promise((r) => setTimeout(r, 1000));
      const job = await getExtractionJob(res.data.job_id);
      if (job.data.status === "completed") {
        extractPreview.value = job.data.result?.yaml_content || "";
        extractedEntryId.value = job.data.result?.entry_id || "";
        break;
      }
      if (job.data.status === "error") {
        extractError.value = job.data.error || "提取失败";
        break;
      }
      tries++;
    }
    if (tries >= 60) extractError.value = "提取超时";
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } } };
    extractError.value = `请求失败: ${err?.response?.data?.detail ?? e}`;
  } finally {
    extracting.value = false;
  }
}
async function doSaveExtract() {
  saving.value = true;
  // 提取完成即已入库（后端在 job 完成时返回 entry_id），此处仅校验再确认
  const entryId = extractedEntryId.value;

  if (!entryId) {
    extractError.value = "提取结果尚未入库，请重新提取。";
    saving.value = false;
    return;
  }

  emit("refresh-stats");

  // 如果是题目导入，记录下来，方便后续追加论文
  if (impType.value === "problem") {
    lastProblemRef.value = entryId;
  }

  const typeLabel =
    { problem: "竞赛真题", method: "方法卡片", template: "框架模板" }[
      impType.value
    ] ?? impType.value;
  savedNotice.value = `已保存到知识库(${typeLabel} · 编号 ${entryId})。可在「管理知识 → ${typeLabel}」或「检索知识」查看。`;
  if (impType.value === "problem") {
    savedNotice.value += "可在下方「上传对应论文」继续追加关联。";
  }

  extractPreview.value = "";
  extractError.value = "";
  impText.value = "";
  impName.value = "";
  clearAll();
  extractedEntryId.value = "";
  saving.value = false;
}

// ── paper upload (independent from problem upload) ───────────────
function paperTriggerFile() {
  paperFileRef.value?.click();
}
function paperOnFileSel(e: Event) {
  const fl = (e.target as HTMLInputElement).files;
  if (fl) paperAddFiles(Array.from(fl));
}
function paperOnDrop(e: DragEvent) {
  paperDragOver.value = false;
  if (e.dataTransfer?.files) paperAddFiles(Array.from(e.dataTransfer.files));
}
function paperAddFiles(newFiles: File[]) {
  const valid = newFiles.filter((f) => f.size <= 10 * 1024 * 1024);
  paperFiles.value = [...paperFiles.value, ...valid];
  if (!paperName.value && valid.length > 0)
    paperName.value = valid[0].name.replace(/\.[^.]+$/, "");
  for (const f of valid) {
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (ext && ["txt", "md", "tex"].includes(ext) && f.size < 500 * 1024) {
      const r = new FileReader();
      r.onload = () => {
        if (!paperText.value) paperText.value = r.result as string;
      };
      r.readAsText(f);
    }
  }
}
function paperRemoveFile(i: number) {
  paperFiles.value.splice(i, 1);
}
function paperClearAll() {
  paperFiles.value = [];
  paperText.value = "";
  paperName.value = "";
  if (paperFileRef.value) paperFileRef.value.value = "";
}

async function paperDoExtract() {
  if (!paperText.value.trim() && paperFiles.value.length === 0) return;
  paperExtracting.value = true;
  paperError.value = "";
  paperPreview.value = "";
  paperExtractedEntryId.value = "";
  savedNotice.value = "";
  try {
    const res = await uploadKnowledge({
      text: paperText.value.trim() || undefined,
      files: paperFiles.value.length > 0 ? paperFiles.value : undefined,
      kb_type: "paper",
      name: paperName.value,
      problem_ref: lastProblemRef.value || undefined,
    });
    let tries = 0;
    while (tries < 60) {
      await new Promise((r) => setTimeout(r, 1000));
      const job = await getExtractionJob(res.data.job_id);
      if (job.data.status === "completed") {
        paperPreview.value = job.data.result?.yaml_content || "";
        paperExtractedEntryId.value = job.data.result?.entry_id || "";
        break;
      }
      if (job.data.status === "error") {
        paperError.value = job.data.error || "提取失败";
        break;
      }
      tries++;
    }
    if (tries >= 60) paperError.value = "提取超时";
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } } };
    paperError.value = `请求失败: ${err?.response?.data?.detail ?? e}`;
  } finally {
    paperExtracting.value = false;
  }
}

async function paperDoSave() {
  paperSaving.value = true;
  // 提取完成即已入库（后端返回 entry_id），此处仅校验再确认
  const entryId = paperExtractedEntryId.value;

  if (!entryId) {
    paperError.value = "提取结果尚未入库，请重新提取。";
    paperSaving.value = false;
    return;
  }

  emit("refresh-stats");
  savedNotice.value = `论文已保存到知识库(真题论文 · 编号 ${entryId})并关联到题目。可在「管理知识 → 真题论文」或「检索知识」查看。`;
  paperPreview.value = "";
  paperError.value = "";
  paperText.value = "";
  paperName.value = "";
  paperClearAll();
  paperExtractedEntryId.value = "";
  paperSaving.value = false;
}
</script>
