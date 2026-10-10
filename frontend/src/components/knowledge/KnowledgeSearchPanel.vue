<template>
  <div>
    <!-- ==================== TAB 1: 检索知识 ==================== -->
    <div class="flex gap-2 mb-5">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input v-model="searchQuery" type="text" placeholder="搜索方法、论文或模板..."
          class="w-full rounded-md border border-border bg-background pl-10 pr-4 py-2.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          @keyup.enter="doSearch" />
      </div>
      <button class="inline-flex items-center rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background hover:bg-foreground/90 disabled:opacity-50 transition-transform hover:scale-[0.98] active:scale-[0.97]"
        :disabled="!searchQuery.trim() || searchLoading" @click="doSearch">
        <Loader2 v-if="searchLoading" class="h-4 w-4 animate-spin" /><span v-else>搜索</span>
      </button>
    </div>
    <!-- 筛选:等宽小标签,非胶囊 -->
    <div class="flex flex-wrap items-center gap-x-5 gap-y-2 mb-6">
      <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">类型</span>
      <button v-for="o in typeOpts" :key="o.value"
        class="font-mono text-[10px] uppercase tracking-wider transition-colors"
        :class="searchFilter === o.value ? 'text-primary' : 'text-muted-foreground/60 hover:text-foreground'"
        @click="searchFilter = o.value">{{ o.label }}</button>
      <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground ml-2">问题</span>
      <button v-for="o in probOpts" :key="o.value"
        class="font-mono text-[10px] uppercase tracking-wider transition-colors"
        :class="searchProblem === o.value ? 'text-primary' : 'text-muted-foreground/60 hover:text-foreground'"
        @click="searchProblem = o.value">{{ o.label }}</button>
    </div>

    <div v-if="searchLoading" class="space-y-3"><div v-for="i in 3" :key="i" class="rounded-md border border-border p-5"><Skeleton class="h-4 w-2/3" /><Skeleton class="h-3 w-full mt-2" /></div></div>
    <div v-else-if="!isBrowsing && searchResults.length === 0" class="text-center py-16 text-muted-foreground text-sm">未找到匹配结果</div>
    <div v-else-if="isBrowsing && visibleResults.length === 0" class="text-center py-16 text-muted-foreground text-sm">知识库暂无条目,切换到「导入知识」添加</div>
    <div v-else class="space-y-3">
      <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{{ isBrowsing ? "全部条目" : "找到" }} {{ visibleResults.length }} 条</p>
      <div v-for="r in visibleResults" :key="r.id" class="cursor-pointer rounded-md border border-border bg-background p-4 hover:border-primary/40 transition-colors" @click="openDetail(r)">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">[{{ typeLabel(r.type) }}]</span>
            <span v-if="r.score != null" class="font-mono text-[10px] text-muted-foreground/70">相关度 {{ ((r.score||0)*100).toFixed(0) }}%</span>
          </div>
          <ChevronRight class="h-4 w-4 text-muted-foreground/40" />
        </div>
        <h3 class="font-display text-sm font-medium mt-2">{{ r.name || r.title }}</h3>
        <p class="text-xs text-muted-foreground mt-1 line-clamp-3 leading-relaxed">{{ r.snippet }}</p>
      </div>
    </div>

    <!-- Detail Dialog -->
    <Dialog :open="!!detailItem" @update:open="detailItem = null">
      <DialogContent class="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle class="font-display">{{ detailItem?.name || detailItem?.title }}</DialogTitle>
          <div v-if="detailRawText" class="flex items-center gap-1 rounded-md bg-muted p-0.5 w-fit mt-2">
            <button class="rounded-sm px-3 py-1 text-xs font-medium transition-all"
              :class="detailViewMode === 'structured' ? 'bg-background shadow-sm' : 'text-muted-foreground hover:text-foreground'"
              @click="detailViewMode = 'structured'">结构化分析</button>
            <button class="rounded-sm px-3 py-1 text-xs font-medium transition-all"
              :class="detailViewMode === 'raw' ? 'bg-background shadow-sm' : 'text-muted-foreground hover:text-foreground'"
              @click="detailViewMode = 'raw'">原始资料</button>
          </div>
        </DialogHeader>
        <!-- Raw view -->
        <pre v-if="detailViewMode === 'raw' && detailRawText" class="text-xs leading-relaxed whitespace-pre-wrap max-h-[60vh] overflow-y-auto rounded-md border bg-muted/30 p-4">{{ detailRawText }}</pre>
        <div v-if="detailViewMode === 'raw' && !detailRawText" class="text-sm text-muted-foreground py-4">该条目没有原始资料（可能不是通过导入创建的）</div>
        <!-- Structured view -->
        <div v-if="detailLoading && detailViewMode === 'structured'" class="space-y-3"><Skeleton class="h-4 w-full" /><Skeleton class="h-4 w-5/6" /></div>
        <div v-else-if="detailData && detailViewMode === 'structured'" class="text-sm space-y-4 py-2">
          <template v-if="detailData.type === 'method_card'">
            <div v-if="detailData.data.unit_id" class="flex items-center gap-2">
              <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">学习单元</span>
              <span class="text-xs text-primary cursor-pointer hover:underline inline-flex items-center gap-1" @click="goToUnit(detailData.data.unit_id)"><BookOpen class="h-3.5 w-3.5" />{{ detailData.data.unit_id }} →</span>
              <span class="text-[10px] text-muted-foreground/60">该卡片的长文即此学习单元正文</span>
            </div>
            <p class="leading-relaxed">{{ detailData.data.principle }}</p>
            <div><h4 class="font-display font-medium text-sm mb-1">适用条件</h4><ul class="list-disc list-inside text-muted-foreground text-sm"><li v-for="c in detailData.data.applicable_when" :key="c">{{ c }}</li></ul></div>
          </template>
          <template v-if="detailData.type === 'paper'">
            <div class="flex items-center gap-3 flex-wrap mb-3">
              <span class="font-mono text-[10px] uppercase tracking-wider border border-border rounded-sm px-2 py-0.5">{{ detailData.data.competition }} {{ detailData.data.year }}·{{ detailData.data.problem_id }}题</span>
              <span class="text-xs text-amber-500 flex items-center gap-0.5">
                <Star v-for="i in (detailData.data.quality_rating || 3)" :key="i" class="h-3 w-3 fill-current" />
              </span>
              <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{{ detailData.data.difficulty_level }}</span>
              <span v-if="detailData.data.problem_ref" class="font-mono text-[10px] uppercase tracking-wider text-emerald-600 cursor-pointer hover:underline inline-flex items-center gap-1" @click="openProblemFromPaper(detailData.data.problem_ref)"><Link2 class="h-3 w-3" />{{ detailData.data.problem_ref }}</span>
              <span v-else class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/50 inline-flex items-center gap-1"><AlertTriangle class="h-3 w-3" />未关联题目</span>
            </div>
            <!-- 问题背景 -->
            <div v-if="detailData.data.problem_context" class="rounded-md border border-border p-4 bg-muted/20">
              <h4 class="font-display font-medium text-sm mb-2">问题背景</h4>
              <p class="text-sm leading-relaxed text-muted-foreground">{{ detailData.data.problem_context }}</p>
            </div>
            <!-- 方法链路 -->
            <div v-if="detailData.data.methodology_chain?.length" class="rounded-md border border-border p-4">
              <h4 class="font-display font-medium text-sm mb-2">建模方法链路</h4>
              <div class="space-y-1.5">
                <div v-for="(step, i) in detailData.data.methodology_chain" :key="i" class="flex items-start gap-2 text-sm">
                  <span class="font-mono text-[10px] text-muted-foreground shrink-0 mt-1">{{ i + 1 }}.</span>
                  <span>{{ step }}</span>
                </div>
              </div>
            </div>
            <!-- 核心公式 -->
            <div v-if="detailData.data.key_formulas?.length" class="rounded-md border border-border p-4">
              <h4 class="font-display font-medium text-sm mb-2">核心公式</h4>
              <div class="space-y-2">
                <div v-for="f in detailData.data.key_formulas" :key="f.name" class="rounded-sm bg-muted/30 p-3">
                  <p class="font-mono text-xs mb-1">{{ f.name }}</p>
                  <p class="font-serif text-sm mb-1 italic">{{ f.latex }}</p>
                  <p class="text-xs text-muted-foreground">{{ f.description }}</p>
                </div>
              </div>
            </div>
            <!-- 算法概要 -->
            <div v-if="detailData.data.algorithm_outline?.length" class="rounded-md border border-border p-4">
              <h4 class="font-display font-medium text-sm mb-2">算法概要</h4>
              <div v-for="(a, i) in detailData.data.algorithm_outline" :key="i" class="mb-3 last:mb-0">
                <p class="text-xs text-muted-foreground mb-1">{{ a.description }}</p>
                <pre class="rounded-sm bg-zinc-950 p-3 text-xs text-zinc-300 overflow-x-auto"><code>{{ a.code }}</code></pre>
              </div>
            </div>
            <!-- 假设分析 -->
            <div v-if="detailData.data.assumption_analysis?.length" class="rounded-md border border-border p-4">
              <h4 class="font-display font-medium text-sm mb-2">假设分析</h4>
              <ul class="space-y-1.5"><li v-for="a in detailData.data.assumption_analysis" :key="a" class="text-sm text-muted-foreground flex items-start gap-2"><span class="text-primary shrink-0">→</span>{{ a }}</li></ul>
            </div>
            <!-- 可复用模式 -->
            <div v-if="detailData.data.reusable_patterns?.length" class="rounded-md border border-emerald-200 bg-emerald-50/30 p-4">
              <h4 class="font-display font-medium text-sm mb-2 text-emerald-800">可复用的建模模式</h4>
              <ul class="space-y-1.5"><li v-for="p in detailData.data.reusable_patterns" :key="p" class="text-sm text-emerald-700 flex items-start gap-2"><Sparkles class="h-3.5 w-3.5 shrink-0 mt-0.5 text-emerald-500" />{{ p }}</li></ul>
            </div>
            <!-- 常见陷阱 -->
            <div v-if="detailData.data.common_pitfalls?.length" class="rounded-md border border-amber-200 bg-amber-50/30 p-4">
              <h4 class="font-display font-medium text-sm mb-2 text-amber-800">常见陷阱</h4>
              <div class="space-y-2"><div v-for="p in detailData.data.common_pitfalls" :key="p.mistake" class="text-sm"><p class="text-amber-700 flex items-start gap-1.5"><AlertTriangle class="h-3.5 w-3.5 shrink-0 mt-0.5" />{{ p.mistake }}</p><p class="text-muted-foreground text-xs mt-0.5">→ {{ p.solution }}</p></div></div>
            </div>
            <!-- 评价 -->
            <div class="border-t border-border pt-3 mt-2">
              <p class="text-sm font-medium">可学之处</p>
              <p class="text-sm text-muted-foreground leading-relaxed mt-1">{{ detailData.data.evaluation?.lessons }}</p>
            </div>
          </template>
          <template v-if="detailData.type === 'template'">
            <div v-for="s in detailData.data.steps" :key="s.step" class="border-l-2 border-border pl-3 py-1">
              <h5 class="font-display font-medium text-sm">§{{ s.step }} {{ s.name }}</h5>
              <ul class="list-disc list-inside text-xs text-muted-foreground mt-1"><li v-for="c in s.checklist" :key="c">{{ c }}</li></ul>
            </div>
          </template>
          <template v-if="detailData.type === 'problem'">
            <div class="flex items-center gap-3 flex-wrap mb-3">
              <span class="font-mono text-[10px] uppercase tracking-wider border border-border rounded-sm px-2 py-0.5">{{ detailData.data.competition }} {{ detailData.data.year }}·{{ detailData.data.problem_id }}题</span>
              <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{{ detailData.data.tags?.difficulty || 'medium' }}</span>
              <span class="text-xs text-muted-foreground" v-if="detailData.data.linked_papers?.length">{{ detailData.data.linked_papers.length }}篇关联论文</span>
            </div>
            <div v-if="detailData.data.background" class="rounded-md border border-border p-4 bg-muted/20">
              <h4 class="font-display font-medium text-sm mb-2">问题背景</h4>
              <p class="text-sm leading-relaxed text-muted-foreground">{{ detailData.data.background }}</p>
            </div>
            <div v-if="detailData.data.objectives?.length" class="rounded-md border border-border p-4">
              <h4 class="font-display font-medium text-sm mb-2">求解目标</h4>
              <ul class="space-y-1"><li v-for="o in detailData.data.objectives" :key="o" class="text-sm text-muted-foreground flex items-start gap-2"><span class="text-primary shrink-0">→</span>{{ o }}</li></ul>
            </div>
            <div v-if="detailData.data.data_description" class="rounded-md border border-border p-4">
              <h4 class="font-display font-medium text-sm mb-2">数据说明</h4>
              <p class="text-sm text-muted-foreground leading-relaxed">{{ detailData.data.data_description }}</p>
            </div>
            <div v-if="detailData.data.full_text" class="rounded-md border border-border p-4">
              <h4 class="font-display font-medium text-sm mb-2">完整题目</h4>
              <p class="text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground">{{ detailData.data.full_text }}</p>
            </div>
          </template>
        </div>
        <DialogFooter><DialogClose class="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors">关闭</DialogClose></DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import {
  type MethodCardDetail,
  type MethodCardSummary,
  type PaperDetail,
  type ProblemDetail,
  type SearchResult,
  type TemplateDetail,
  getMethod,
  getMethodRaw,
  getPaper,
  getPaperRaw,
  getProblem,
  getProblemRaw,
  getTemplate,
  getTemplateRaw,
  listMethods,
  listPapers,
  listProblems,
  listTemplates,
  searchKB,
} from "@/apis/knowledgeApi";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle,
  BookOpen,
  ChevronRight,
  Link2,
  Loader2,
  Search,
  Sparkles,
  Star,
} from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

// ── Tab 1: Search ───────────────────────────────────────────────
const searchQuery = ref("");
const searchFilter = ref("");
const searchProblem = ref("");
const searchLoading = ref(false);
const searchDone = ref(false);
const searchResults = ref<SearchResult[]>([]);
const detailItem = ref<SearchResult | null>(null);
const detailLoading = ref(false);
/** 详情条目：判别联合（模板 v-if 按 type 收窄 data 类型，替代 as any） */
type DetailEntry =
  | { type: "method_card"; data: MethodCardDetail }
  | { type: "paper"; data: PaperDetail }
  | { type: "template"; data: TemplateDetail }
  | { type: "problem"; data: ProblemDetail };
const detailData = ref<DetailEntry | null>(null);
const detailRawText = ref("");
const detailViewMode = ref<"structured" | "raw">("structured");
const typeOpts = [
  { label: "全部", value: "" },
  { label: "方法卡片", value: "method_card" },
  { label: "真题论文", value: "paper" },
  { label: "框架模板", value: "template" },
  { label: "竞赛真题", value: "problem" },
];
const probOpts = [
  { label: "全部", value: "" },
  { label: "优化", value: "optimization" },
  { label: "预测", value: "prediction" },
  { label: "评价", value: "evaluation" },
  { label: "统计", value: "statistics" },
];
function typeLabel(t: string) {
  return (
    {
      method_card: "方法卡片",
      paper: "真题论文",
      template: "框架模板",
      problem: "竞赛真题",
    }[t] || t
  );
}
function badgeClass(t: string) {
  return (
    {
      method_card: "bg-blue-100 text-blue-700",
      paper: "bg-purple-100 text-purple-700",
      template: "bg-green-100 text-green-700",
    }[t] || "bg-muted"
  );
}
async function doSearch() {
  if (!searchQuery.value.trim()) return;
  searchLoading.value = true;
  searchDone.value = true;
  try {
    const r = await searchKB({
      q: searchQuery.value.trim(),
      type: searchFilter.value || undefined,
      problem_type: searchProblem.value || undefined,
      k: 10,
    });
    searchResults.value = r.data.results;
  } catch {
    searchResults.value = [];
  } finally {
    searchLoading.value = false;
  }
}

// ── 默认浏览全部（不搜索也能看到知识库存量）──────────────────
const browseAll = ref<SearchResult[]>([]);
const isBrowsing = computed(
  () => !searchDone.value || !searchQuery.value.trim(),
);
const visibleResults = computed<SearchResult[]>(() => {
  const list = isBrowsing.value ? browseAll.value : searchResults.value;
  return searchFilter.value
    ? list.filter((r) => r.type === searchFilter.value)
    : list;
});
async function loadBrowseAll() {
  const items: SearchResult[] = [];
  // 分开请求：单个失败不影响其他类型
  try {
    const m = await listMethods();
    items.push(
      ...(m.data ?? []).map((c) => ({
        id: c.id,
        type: "method_card" as const,
        name: c.name,
        title: c.name,
        // summary 接口未含 principle，运行时数据携带（结构断言补类型）
        snippet: (
          (c as MethodCardSummary & { principle?: string }).principle ?? ""
        ).slice(0, 120),
        score: null,
      })),
    );
  } catch (e) {
    console.warn("listMethods failed:", e);
  }
  try {
    const p = await listPapers();
    items.push(
      ...(p.data ?? []).map((x) => ({
        id: x.id,
        type: "paper" as const,
        name: x.title,
        title: x.title,
        snippet: `${x.year} / ${x.competition} / ${x.problem_id || ""}`,
        score: null,
      })),
    );
  } catch (e) {
    console.warn("listPapers failed:", e);
  }
  try {
    const t = await listTemplates();
    items.push(
      ...(t.data ?? []).map((x) => ({
        id: x.id,
        type: "template" as const,
        name: x.name,
        title: x.name,
        snippet: (x.applicable_to ?? []).join(", "),
        score: null,
      })),
    );
  } catch (e) {
    console.warn("listTemplates failed:", e);
  }
  try {
    const pr = await listProblems();
    items.push(
      ...(pr.data ?? []).map((x) => ({
        id: x.id,
        type: "problem" as const,
        name: x.title,
        title: x.title,
        snippet: `${x.year} / ${x.competition} / ${x.problem_id || ""}`,
        score: null,
      })),
    );
  } catch (e) {
    console.warn("listProblems failed:", e);
  }
  browseAll.value = items;
}
// 清空搜索词时回到浏览模式
watch(searchQuery, (v) => {
  if (!v.trim()) searchDone.value = false;
});
async function openDetail(r: SearchResult) {
  detailItem.value = r;
  detailLoading.value = true;
  detailData.value = null;
  detailRawText.value = "";
  detailViewMode.value = "structured";
  try {
    if (r.type === "method_card") {
      const res = await getMethod(r.id);
      detailData.value = { type: "method_card", data: res.data };
    } else if (r.type === "paper") {
      const res = await getPaper(r.id);
      detailData.value = { type: "paper", data: res.data };
    } else if (r.type === "problem") {
      const res = await getProblem(r.id);
      detailData.value = { type: "problem", data: res.data };
    } else {
      const res = await getTemplate(r.id);
      detailData.value = { type: "template", data: res.data };
    }
  } catch {
    /* ignore */
  } finally {
    detailLoading.value = false;
  }
  // Fetch raw text in background
  try {
    if (r.type === "method_card") {
      const rr = await getMethodRaw(r.id);
      detailRawText.value = rr.data.raw_text;
    } else if (r.type === "paper") {
      const rr = await getPaperRaw(r.id);
      detailRawText.value = rr.data.raw_text;
    } else if (r.type === "problem") {
      const rr = await getProblemRaw(r.id);
      detailRawText.value = rr.data.raw_text;
    } else {
      const rr = await getTemplateRaw(r.id);
      detailRawText.value = rr.data.raw_text;
    }
  } catch {
    /* no raw text available */
  }
}
const router = useRouter();

/** 方案 C：从知识库卡片跳转到关联学习单元（卡片长文即单元正文）。 */
function goToUnit(unitId: string) {
  router.push(`/learn/${unitId}`);
}
async function openProblemFromPaper(problemRef: string) {
  // 打开关联的题目详情
  detailItem.value = {
    id: problemRef,
    type: "problem",
    name: "",
    title: "",
    snippet: "",
    score: null,
  };
  detailLoading.value = true;
  detailData.value = null;
  detailRawText.value = "";
  detailViewMode.value = "structured";
  try {
    const res = await getProblem(problemRef);
    detailData.value = { type: "problem", data: res.data };
  } catch {
    /* ignore */
  } finally {
    detailLoading.value = false;
  }
  try {
    const rr = await getProblemRaw(problemRef);
    detailRawText.value = rr.data.raw_text;
  } catch {
    /* */
  }
}

// 进入面板时加载默认浏览列表
onMounted(() => {
  loadBrowseAll();
});
</script>
