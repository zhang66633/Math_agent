<template>
  <div>
    <!-- ==================== TAB 2: 管理知识 ==================== -->
    <div class="flex items-center gap-x-5 gap-y-2 mb-5 flex-wrap">
      <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">类型</span>
      <button v-for="o in mgrTypes" :key="o.value"
        class="font-mono text-[10px] uppercase tracking-wider transition-colors"
        :class="mgrType === o.value ? 'text-primary' : 'text-muted-foreground/60 hover:text-foreground'"
        @click="mgrType = o.value">{{ o.label }}</button>
      <span class="flex-1" />
      <button class="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent transition-colors" @click="loadMgrList"><RefreshCw class="h-3 w-3" />刷新</button>
    </div>

    <div v-if="mgrLoading" class="space-y-3"><div v-for="i in 5" :key="i" class="rounded-md border border-border p-4"><Skeleton class="h-4 w-3/4" /></div></div>
    <div v-else-if="mgrError" class="flex flex-col items-center justify-center gap-2 py-12 border border-dashed border-border rounded-md text-muted-foreground text-sm">
      <span class="flex items-center gap-1.5"><AlertTriangle class="h-4 w-4 text-amber-500" />{{ mgrError }}</span>
      <button class="mt-1 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent transition-colors" @click="loadMgrList">重试</button>
    </div>
    <div v-else-if="mgrEntries.length === 0" class="text-center py-12 border border-dashed border-border rounded-md text-muted-foreground text-sm">暂无条目,切换到「导入知识」添加</div>
    <div v-else class="divide-y divide-border border border-border rounded-md">
      <div v-for="e in mgrEntries" :key="e.id" class="flex items-center gap-3 bg-background px-4 py-3 hover:bg-accent/30 group transition-colors">
        <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground shrink-0">[{{ mgrTypeLabel }}]</span>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium truncate">{{ e.name || e.title }}</p>
          <p class="font-mono text-[10px] text-muted-foreground/70 mt-0.5">{{ mgrSub(e) }}</p>
        </div>
        <div v-if="isContributor" class="flex gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button class="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground" title="编辑" @click="openEdit(e)"><Pencil class="h-3.5 w-3.5" /></button>
          <button class="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive" title="删除" @click="confirmDel(e)"><Trash2 class="h-3.5 w-3.5" /></button>
        </div>
      </div>
    </div>
    <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/70 text-center pt-3">共 {{ mgrEntries.length }} 条</p>
    <div v-if="isContributor" class="mt-8 pt-6 border-t text-center">
      <button class="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground/50 hover:text-muted-foreground mx-auto transition-colors" :disabled="reindexing" @click="doReindex">
        <RefreshCw v-if="reindexing" class="h-3 w-3 animate-spin" /><Database v-else class="h-3 w-3" />{{ reindexing ? '重建中' : '重建向量索引' }}
      </button>
    </div>

    <!-- Edit Dialog — 全字段表单 -->
    <Dialog :open="editOpen" @update:open="editOpen = $event">
      <DialogContent class="max-w-3xl max-h-[88vh] overflow-y-auto">
        <DialogHeader><DialogTitle class="font-display">编辑{{ mgrTypeLabel }}</DialogTitle></DialogHeader>
        <div v-if="editLoading" class="flex items-center justify-center py-16"><Loader2 class="h-5 w-5 animate-spin text-muted-foreground" /></div>
        <div v-else class="space-y-4 text-sm py-2">

          <!-- ===== 方法卡片 ===== -->
          <template v-if="mgrType === 'method'">
            <p class="font-mono text-[10px] text-muted-foreground/70">ID: {{ editForm.id }}</p>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">名称</label><Input v-model="editForm.name" class="mt-1" /></div>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">核心原理</label><Textarea v-model="editForm.principle" rows="5" class="mt-1" /></div>
            <ArrayEditor v-model="editForm.category" label="分类" placeholder="优化 / 预测 / 统计..." />
            <ArrayEditor v-model="editForm.applicable_when" label="适用条件" />
            <ArrayEditor v-model="editForm.typical_scenarios" label="典型场景" />
            <ArrayEditor v-model="editForm.not_applicable_when" label="不适用情况" />
            <ArrayEditor v-model="editForm.common_mistakes" label="常见错误与对策" :fields="[{key:'mistake',label:'错误'},{key:'solution',label:'对策'}]" empty-value="{mistake:'',solution:''}" />
            <ArrayEditor v-model="editForm.code_snippets" label="代码示例" :fields="[{key:'language',label:'语言'},{key:'description',label:'说明'},{key:'code',label:'代码',type:'textarea'}]" empty-value="{language:'',description:'',code:''}" />
            <ArrayEditor v-model="editForm.formulas" label="核心公式" :fields="[{key:'name',label:'名称'},{key:'latex',label:'LaTeX'},{key:'description',label:'说明'}]" empty-value="{name:'',latex:'',description:''}" />
            <ArrayEditor v-model="editForm.related_cards" label="关联方法ID" />
          </template>

          <!-- ===== 论文 ===== -->
          <template v-if="mgrType === 'paper'">
            <p class="font-mono text-[10px] text-muted-foreground/70">ID: {{ editForm.id }}</p>
            <div class="grid grid-cols-3 gap-2">
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">年份</label><Input v-model.number="editForm.year" type="number" class="mt-1" /></div>
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">竞赛</label><Input v-model="editForm.competition" class="mt-1" /></div>
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">题号</label><Input v-model="editForm.problem_id" class="mt-1" /></div>
            </div>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">标题</label><Input v-model="editForm.title" class="mt-1" /></div>
            <div class="grid grid-cols-2 gap-2">
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">评分 1-5</label><Input v-model.number="editForm.quality_rating" type="number" min="1" max="5" class="mt-1" /></div>
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">关联题目</label><Input v-model="editForm.problem_ref" class="mt-1" /></div>
            </div>
            <ArrayEditor v-model="editForm.tags_problem_type" label="问题类型" />
            <ArrayEditor v-model="editForm.tags_core_models" label="核心方法" />
            <h4 class="font-display text-xs uppercase tracking-wider text-muted-foreground pt-1">分析</h4>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">问题摘要</label><Textarea v-model="editForm.analysis_problem_summary" rows="4" class="mt-1" /></div>
            <ArrayEditor v-model="editForm.analysis_key_assumptions" label="关键假设" />
            <ArrayEditor v-model="editForm.analysis_decision_variables" label="决策变量" />
            <div class="grid grid-cols-2 gap-2">
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">目标函数</label><Textarea v-model="editForm.analysis_objective" rows="2" class="mt-1" /></div>
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">约束条件</label><Textarea v-model="editForm.analysis_constraints" rows="2" class="mt-1" /></div>
            </div>
            <h4 class="font-display text-xs uppercase tracking-wider text-muted-foreground pt-1">模型</h4>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">建模思路</label><Textarea v-model="editForm.model_approach" rows="4" class="mt-1" /></div>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">创新点</label><Input v-model="editForm.model_innovation" class="mt-1" /></div>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">求解方法</label><Input v-model="editForm.model_solution_method" class="mt-1" /></div>
            <h4 class="font-display text-xs uppercase tracking-wider text-muted-foreground pt-1">评价</h4>
            <ArrayEditor v-model="editForm.evaluation_strengths" label="优点" />
            <ArrayEditor v-model="editForm.evaluation_weaknesses" label="缺点" />
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">可学之处</label><Textarea v-model="editForm.evaluation_lessons" rows="3" class="mt-1" /></div>
            <ArrayEditor v-model="editForm.methodology_chain" label="方法链路" />
          </template>

          <!-- ===== 模板 ===== -->
          <template v-if="mgrType === 'template'">
            <p class="font-mono text-[10px] text-muted-foreground/70">ID: {{ editForm.id }}</p>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">名称</label><Input v-model="editForm.name" class="mt-1" /></div>
            <ArrayEditor v-model="editForm.applicable_to" label="适用类型" />
            <ArrayEditor v-model="editForm.steps" label="引导步骤" :fields="[{key:'name',label:'步骤名'},{key:'guiding_questions',label:'引导问题',type:'textarea'},{key:'decision_tree',label:'决策分支',type:'textarea'},{key:'checklist',label:'检查清单',type:'textarea'}]" empty-value="{name:'',guiding_questions:'',decision_tree:'',checklist:''}" />
          </template>

          <!-- ===== 赛题 ===== -->
          <template v-if="mgrType === 'problem'">
            <p class="font-mono text-[10px] text-muted-foreground/70">ID: {{ editForm.id }}</p>
            <div class="grid grid-cols-3 gap-2">
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">年份</label><Input v-model.number="editForm.year" type="number" class="mt-1" /></div>
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">竞赛</label><Input v-model="editForm.competition" class="mt-1" /></div>
              <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">题号</label><Input v-model="editForm.problem_id" class="mt-1" /></div>
            </div>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">标题</label><Input v-model="editForm.title" class="mt-1" /></div>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">问题背景</label><Textarea v-model="editForm.background" rows="4" class="mt-1" /></div>
            <ArrayEditor v-model="editForm.objectives" label="求解目标" />
            <ArrayEditor v-model="editForm.tags_problem_type" label="题型标签" />
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">数据描述</label><Input v-model="editForm.data_description" class="mt-1" /></div>
            <div><label class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">原文全文</label><Textarea v-model="editForm.full_text" rows="6" class="mt-1" /></div>
            <ArrayEditor v-model="editForm.deliverables" label="提交物" />
          </template>
        </div>
        <DialogFooter>
          <button class="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors" @click="editOpen = false">取消</button>
          <button class="rounded-md bg-foreground px-4 py-2 text-sm text-background hover:bg-foreground/90 disabled:opacity-50 transition-transform hover:scale-[0.98] active:scale-[0.97]" :disabled="editSaving" @click="doEditSave">
            <Loader2 v-if="editSaving" class="h-4 w-4 mr-1 animate-spin" />{{ editSaving ? '保存中' : '保存' }}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Delete Confirm -->
    <Dialog :open="delOpen" @update:open="delOpen = $event">
      <DialogContent class="max-w-sm">
        <DialogHeader><DialogTitle class="font-display">确认删除</DialogTitle><DialogDescription>确定删除 "{{ delTarget?.name || delTarget?.title }}"?不可撤销。</DialogDescription></DialogHeader>
        <DialogFooter>
          <button class="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors" @click="delOpen = false">取消</button>
          <button class="rounded-md bg-destructive px-4 py-2 text-sm text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50 transition-transform hover:scale-[0.98] active:scale-[0.97]" :disabled="deleting" @click="doDelete">
            <Loader2 v-if="deleting" class="h-4 w-4 mr-1 animate-spin" />{{ deleting ? '删除中' : '确认删除' }}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import {
  type MethodCardDetail,
  type MethodCardSummary,
  type PaperDetail,
  type PaperSummary,
  type ProblemDetail,
  type ProblemSummary,
  type TemplateDetail,
  type TemplateSummary,
  deleteMethod,
  deletePaper,
  deleteProblem,
  deleteTemplate,
  getMethod,
  getPaper,
  getProblem,
  getTemplate,
  listMethods,
  listPapers,
  listProblems,
  listTemplates,
  reindexKB,
  updateMethod,
  updatePaper,
  updateProblem,
  updateTemplate,
} from "@/apis/knowledgeApi";
import ArrayEditor from "@/components/ArrayEditor.vue";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertTriangle,
  Database,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
} from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";

const props = defineProps<{
  isContributor: boolean;
  initialSubType?: string;
}>();
const emit = defineEmits<(e: "refresh-stats") => void>();

// ── Tab 2: Manage ───────────────────────────────────────────────
/** 管理列表条目：四类 summary 的宽松合并视图（模板按 mgrType 取字段） */
interface MgrEntry {
  id: string;
  name?: string;
  title?: string;
  year?: number;
  competition?: string;
  problem_id?: string;
  category?: string[];
  quality_rating?: number;
  problem_ref?: string;
  linked_papers_count?: number;
  steps_count?: number;
}

/** 编辑表单：四类详情的展平字段（数组用 unknown[] 与 ArrayEditor v-model 对齐） */
interface EditForm {
  id: string;
  name?: string;
  title?: string;
  principle?: string;
  year?: number;
  competition?: string;
  problem_id?: string;
  quality_rating?: number;
  problem_ref?: string;
  background?: string;
  data_description?: string;
  full_text?: string;
  // method
  category?: unknown[];
  applicable_when?: unknown[];
  typical_scenarios?: unknown[];
  not_applicable_when?: unknown[];
  common_mistakes?: unknown[];
  code_snippets?: unknown[];
  formulas?: unknown[];
  related_cards?: unknown[];
  related_papers?: unknown[];
  // paper（analysis/model/evaluation/tags 展平）
  analysis?: unknown;
  model?: unknown;
  evaluation?: unknown;
  analysis_problem_summary?: string;
  analysis_key_assumptions?: unknown[];
  analysis_decision_variables?: unknown[];
  analysis_objective?: string;
  analysis_constraints?: string;
  model_approach?: string;
  model_innovation?: string;
  model_solution_method?: string;
  evaluation_strengths?: unknown[];
  evaluation_weaknesses?: unknown[];
  evaluation_lessons?: string;
  tags?: Record<string, string[]>;
  tags_problem_type?: unknown[];
  tags_core_models?: unknown[];
  methodology_chain?: unknown[];
  problem_context?: string;
  key_formulas?: unknown[];
  algorithm_outline?: unknown[];
  assumption_analysis?: unknown[];
  reusable_patterns?: unknown[];
  common_pitfalls?: unknown[];
  // template
  steps?: unknown[];
  applicable_to?: unknown[];
  // problem
  objectives?: unknown[];
  deliverables?: unknown[];
  // 其余 detail 字段透传
  [key: string]: unknown;
}

const mgrType = ref("method");
const mgrEntries = ref<MgrEntry[]>([]);
const mgrLoading = ref(false);
const mgrError = ref("");
const mgrTypes = [
  { label: "方法卡片", value: "method" },
  { label: "真题论文", value: "paper" },
  { label: "框架模板", value: "template" },
  { label: "竞赛真题", value: "problem" },
];
const mgrTypeLabel = computed(
  () =>
    ({ method: "方法", paper: "论文", template: "模板", problem: "题目" })[
      mgrType.value
    ],
);
const mgrBadgeClass = computed(
  () =>
    ({
      method: "bg-blue-100 text-blue-700",
      paper: "bg-purple-100 text-purple-700",
      template: "bg-green-100 text-green-700",
      problem: "bg-amber-100 text-amber-700",
    })[mgrType.value],
);
function mgrSub(e: MgrEntry) {
  if (mgrType.value === "method") return (e.category ?? []).join(", ");
  if (mgrType.value === "paper")
    return `${e.year ?? ""} ${e.competition ?? ""} ${e.problem_id ?? ""} · 评分${e.quality_rating ?? 3}${e.problem_ref ? " · 已关联题目" : " · 未关联题目"}`;
  if (mgrType.value === "problem")
    return `${e.year ?? ""} ${e.competition ?? ""} ${e.problem_id ?? ""} · ${e.linked_papers_count ?? 0}篇论文`;
  return `${e.steps_count ?? 0} 个步骤`;
}
/** 加载当前类型的条目列表,带瞬时故障重试;失败不覆盖旧数据,只置错误态。 */
async function loadMgrList() {
  mgrLoading.value = true;
  mgrError.value = "";
  try {
    for (let attempt = 0; ; attempt++) {
      try {
        if (mgrType.value === "method") {
          const r = await listMethods();
          mgrEntries.value = r.data ?? [];
        } else if (mgrType.value === "paper") {
          const r = await listPapers();
          mgrEntries.value = r.data ?? [];
        } else if (mgrType.value === "problem") {
          const r = await listProblems();
          mgrEntries.value = r.data ?? [];
        } else {
          const r = await listTemplates();
          mgrEntries.value = r.data ?? [];
        }
        return;
      } catch (err) {
        if (attempt >= 2) throw err;
        await new Promise((r) => setTimeout(r, 600 * (attempt + 1)));
      }
    }
  } catch {
    mgrError.value = "条目加载失败,请检查后端服务后重试";
  } finally {
    mgrLoading.value = false;
  }
}
// 挂载时立即加载(mgrType 默认为 method,watch 不会触发首次加载);
// 若父页指定了要打开的子页签(导入成功后跳转),切过去由 watch 触发加载,避免重复请求
onMounted(() => {
  if (props.initialSubType && props.initialSubType !== mgrType.value) {
    mgrType.value = props.initialSubType;
  } else {
    loadMgrList();
  }
});
watch(mgrType, () => loadMgrList());

// Edit
const editOpen = ref(false);
const editSaving = ref(false);
const editLoading = ref(false);
const editForm = ref<EditForm>({ id: "" });
async function openEdit(e: MgrEntry) {
  editLoading.value = true;
  editOpen.value = true;
  editForm.value = { ...e };
  try {
    let detail:
      | MethodCardDetail
      | PaperDetail
      | TemplateDetail
      | ProblemDetail
      | null = null;
    if (mgrType.value === "method") detail = (await getMethod(e.id)).data;
    else if (mgrType.value === "paper") detail = (await getPaper(e.id)).data;
    else if (mgrType.value === "template")
      detail = (await getTemplate(e.id)).data;
    else if (mgrType.value === "problem")
      detail = (await getProblem(e.id)).data;
    if (detail) editForm.value = { ...e, ...detail } as EditForm;
  } catch (err) {
    console.error("Failed to load detail:", err);
  } finally {
    editLoading.value = false;
  }
  const t: EditForm = { ...editForm.value };
  if (mgrType.value === "method") {
    t.category = Array.isArray(t.category) ? [...t.category] : [];
    t.applicable_when = Array.isArray(t.applicable_when)
      ? [...t.applicable_when]
      : [];
    t.typical_scenarios = Array.isArray(t.typical_scenarios)
      ? [...t.typical_scenarios]
      : [];
    t.not_applicable_when = Array.isArray(t.not_applicable_when)
      ? [...t.not_applicable_when]
      : [];
    t.common_mistakes = Array.isArray(t.common_mistakes)
      ? t.common_mistakes.map((m) => ({ ...(m as Record<string, unknown>) }))
      : [];
    t.code_snippets = Array.isArray(t.code_snippets)
      ? t.code_snippets.map((c) => ({ ...(c as Record<string, unknown>) }))
      : [];
    t.formulas = Array.isArray(t.formulas)
      ? t.formulas.map((f) => ({ ...(f as Record<string, unknown>) }))
      : [];
    t.related_cards = Array.isArray(t.related_cards)
      ? [...t.related_cards]
      : [];
    t.related_papers = Array.isArray(t.related_papers)
      ? [...t.related_papers]
      : [];
  }
  if (mgrType.value === "paper") {
    const ana = (t.analysis ?? {}) as {
      problem_summary?: string;
      key_assumptions?: string[];
      decision_variables?: string;
      objective?: string;
      constraints?: string;
    };
    t.analysis_problem_summary = ana.problem_summary ?? "";
    t.analysis_key_assumptions = Array.isArray(ana.key_assumptions)
      ? [...ana.key_assumptions]
      : [];
    t.analysis_decision_variables = ana.decision_variables
      ? ana.decision_variables
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : [];
    t.analysis_objective = ana.objective ?? "";
    t.analysis_constraints = ana.constraints ?? "";
    const mdl = (t.model ?? {}) as {
      approach?: string;
      innovation?: string;
      solution_method?: string;
    };
    t.model_approach = mdl.approach ?? "";
    t.model_innovation = mdl.innovation ?? "";
    t.model_solution_method = mdl.solution_method ?? "";
    const eva = (t.evaluation ?? {}) as {
      strengths?: string[];
      weaknesses?: string[];
      lessons?: string;
    };
    t.evaluation_strengths = Array.isArray(eva.strengths)
      ? [...eva.strengths]
      : [];
    t.evaluation_weaknesses = Array.isArray(eva.weaknesses)
      ? [...eva.weaknesses]
      : [];
    t.evaluation_lessons = eva.lessons ?? "";
    const tags = (t.tags ?? {}) as {
      problem_type?: string[];
      core_models?: string[];
    };
    t.tags_problem_type = Array.isArray(tags.problem_type)
      ? [...tags.problem_type]
      : [];
    t.tags_core_models = Array.isArray(tags.core_models)
      ? [...tags.core_models]
      : [];
    t.methodology_chain = Array.isArray(t.methodology_chain)
      ? [...t.methodology_chain]
      : [];
    t.problem_context = t.problem_context ?? "";
    t.key_formulas = Array.isArray(t.key_formulas)
      ? t.key_formulas.map((f) => ({ ...(f as Record<string, unknown>) }))
      : [];
    t.algorithm_outline = Array.isArray(t.algorithm_outline)
      ? t.algorithm_outline.map((a) => ({ ...(a as Record<string, unknown>) }))
      : [];
    t.assumption_analysis = Array.isArray(t.assumption_analysis)
      ? [...t.assumption_analysis]
      : [];
    t.reusable_patterns = Array.isArray(t.reusable_patterns)
      ? [...t.reusable_patterns]
      : [];
    t.common_pitfalls = Array.isArray(t.common_pitfalls)
      ? t.common_pitfalls.map((p) => ({ ...(p as Record<string, unknown>) }))
      : [];
  }
  if (mgrType.value === "template") {
    t.steps = Array.isArray(t.steps)
      ? t.steps.map((s) => ({ ...(s as Record<string, unknown>) }))
      : [];
    t.applicable_to = Array.isArray(t.applicable_to)
      ? [...t.applicable_to]
      : [];
  }
  if (mgrType.value === "problem") {
    const tags = (t.tags ?? {}) as { problem_type?: string[] };
    t.tags_problem_type = Array.isArray(tags.problem_type)
      ? [...tags.problem_type]
      : [];
    t.objectives = Array.isArray(t.objectives) ? [...t.objectives] : [];
    t.deliverables = Array.isArray(t.deliverables) ? [...t.deliverables] : [];
  }
  editForm.value = t;
}
async function doEditSave() {
  editSaving.value = true;
  try {
    const id = editForm.value.id;
    const data: Record<string, unknown> = { ...editForm.value };
    if (mgrType.value === "method") {
      data.id = undefined;
      await updateMethod(id, data);
    } else if (mgrType.value === "paper") {
      data.analysis = {
        problem_summary: data.analysis_problem_summary,
        key_assumptions: data.analysis_key_assumptions,
        decision_variables: data.analysis_decision_variables,
        objective: data.analysis_objective,
        constraints: data.analysis_constraints,
      };
      data.model = {
        approach: data.model_approach,
        innovation: data.model_innovation,
        solution_method: data.model_solution_method,
      };
      data.evaluation = {
        strengths: data.evaluation_strengths,
        weaknesses: data.evaluation_weaknesses,
        lessons: data.evaluation_lessons,
      };
      data.tags = {
        problem_type: data.tags_problem_type,
        core_models: data.tags_core_models,
      };
      for (const k of [
        "analysis_problem_summary",
        "analysis_key_assumptions",
        "analysis_decision_variables",
        "analysis_objective",
        "analysis_constraints",
        "model_approach",
        "model_innovation",
        "model_solution_method",
        "evaluation_strengths",
        "evaluation_weaknesses",
        "evaluation_lessons",
        "tags_problem_type",
        "tags_core_models",
      ]) {
        data[k] = undefined;
      }
      await updatePaper(id, data);
    } else if (mgrType.value === "template") {
      data.id = undefined;
      await updateTemplate(id, data);
    } else if (mgrType.value === "problem") {
      data.tags = {
        ...((data.tags as Record<string, unknown> | undefined) ?? {}),
        problem_type: data.tags_problem_type,
      };
      data.tags_problem_type = undefined;
      data.id = undefined;
      await updateProblem(id, data);
    }
    editOpen.value = false;
    await loadMgrList();
    emit("refresh-stats");
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } } };
    alert(`保存失败: ${err?.response?.data?.detail ?? e}`);
  } finally {
    editSaving.value = false;
  }
}

// Delete
const delOpen = ref(false);
const delTarget = ref<MgrEntry | null>(null);
const deleting = ref(false);
function confirmDel(e: MgrEntry) {
  delTarget.value = e;
  delOpen.value = true;
}
async function doDelete() {
  deleting.value = true;
  try {
    const id = delTarget.value?.id;
    if (!id) return;
    if (mgrType.value === "method") await deleteMethod(id);
    else if (mgrType.value === "paper") await deletePaper(id);
    else if (mgrType.value === "problem") await deleteProblem(id);
    else await deleteTemplate(id);
    delOpen.value = false;
    delTarget.value = null;
    await loadMgrList();
    emit("refresh-stats");
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } } };
    alert(`删除失败: ${err?.response?.data?.detail ?? e}`);
  } finally {
    deleting.value = false;
  }
}

// Reindex
const reindexing = ref(false);
async function doReindex() {
  reindexing.value = true;
  try {
    const r = await reindexKB();
    alert(r.data.message);
    emit("refresh-stats");
  } catch {
    alert("重建索引失败");
  } finally {
    reindexing.value = false;
  }
}
</script>
