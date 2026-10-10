<template>
  <div class="bg-grid-paper h-full overflow-y-auto">
    <!-- Access denied banner -->
    <div v-if="deniedMessage" class="mx-auto max-w-4xl px-6 sm:px-10 pt-4">
      <div class="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
        <ShieldAlert class="h-5 w-5 shrink-0 text-amber-600 mt-0.5" />
        <p class="text-sm text-amber-800 flex-1">{{ deniedMessage }}</p>
        <button class="shrink-0 text-amber-500 hover:text-amber-700 transition-colors" @click="dismissDenied">
          <X class="h-4 w-4" />
        </button>
      </div>
    </div>

    <!-- API Key 快速配置区域 -->
    <div class="mx-auto max-w-4xl px-6 sm:px-10 pt-4">
      <div v-if="myKey.has_key" class="flex items-center gap-3 rounded-md border border-green-200 bg-green-50 px-4 py-2.5">
        <CheckCircle2 class="h-5 w-5 shrink-0 text-green-600" />
        <span class="text-sm text-green-800 font-medium">API Key 已激活</span>
        <span class="text-xs text-green-700 font-mono">{{ myKey.key?.masked_key }}</span>
        <span class="text-xs text-green-600">· {{ myKey.key?.provider }} · {{ myKey.key?.model_name }}</span>
        <button class="ml-auto text-xs text-green-600 hover:text-green-800 underline shrink-0" @click="showKeyInput = !showKeyInput">
          {{ showKeyInput ? '取消' : '更换' }}
        </button>
      </div>

      <div v-if="!myKey.has_key || showKeyInput" class="rounded-md border border-border bg-card p-4">
        <div class="flex items-center gap-3 flex-wrap">
          <Key class="h-5 w-5 shrink-0 text-muted-foreground" />
          <input
            v-model="keyInput"
            type="password"
            placeholder="粘贴你的 API Key，例如 sk-..."
            class="flex-1 min-w-[260px] h-10 rounded-md border border-input bg-background px-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            @keydown.enter="activateKey"
          />
          <button
            class="inline-flex items-center gap-1.5 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background hover:bg-foreground/90 transition-colors disabled:opacity-50 shrink-0"
            :disabled="!keyInput.trim() || activating"
            @click="activateKey"
          >
            <Loader2 v-if="activating" class="h-4 w-4 animate-spin" />
            <Zap v-else class="h-4 w-4" />
            {{ myKey.has_key ? '更新并激活' : '激活 Key' }}
          </button>
        </div>
        <p class="mt-2 text-xs text-muted-foreground">
          支持 DeepSeek、OpenAI、Anthropic 等 OpenAI 兼容 API。
          从 <a href="https://platform.deepseek.com" target="_blank" class="underline">platform.deepseek.com</a> 获取 Key，Key 仅保存在本地服务器。
        </p>
        <p v-if="activateError" class="mt-1 text-xs text-red-600">{{ activateError }}</p>
      </div>
    </div>

    <div class="mx-auto max-w-4xl px-6 sm:px-10">

      <!-- 标题区 -->
      <header class="pt-20 pb-16 sm:pt-28 sm:pb-20">
        <p class="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground mb-6">
          ·0 &nbsp; 工作台
        </p>
        <h1 class="font-display text-5xl sm:text-6xl font-medium tracking-tight leading-[1.05]">
          数学建模
        </h1>
        <p class="font-display italic text-2xl sm:text-3xl text-muted-foreground mt-3 leading-[1.2] pb-1">
          智能体团队，陪你从入门到竞赛
        </p>
        <p class="mt-8 text-base text-muted-foreground max-w-xl leading-relaxed">
          论文写作与学习训练双线并行。建模师教方法、求解器写代码、编辑改论文——智能体团队分工协作。
        </p>
      </header>

      <!-- ·1 论文工作台 -->
      <section class="pb-20">
        <div class="section-rule mb-10">
          <span class="font-mono text-xs tracking-wider">·1 &nbsp; 论文工作台</span>
        </div>

        <!-- 对话 — 主力入口，大卡片 -->
        <div class="grid grid-cols-1 lg:grid-cols-5 gap-8 lg:gap-12 mb-12">
          <div class="lg:col-span-3 flex flex-col justify-center">
            <span class="font-mono text-[10px] text-primary tracking-widest uppercase mb-3">核心入口</span>
            <h2 class="font-display text-3xl font-medium">与智能体对话</h2>
            <p class="mt-3 text-sm text-muted-foreground leading-relaxed max-w-sm">
              自由对话推进建模讨论。AI 调用知识库检索、数学计算、代码执行，每一次推理都可追溯。
            </p>
            <button
              class="mt-6 inline-flex items-center gap-2 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background hover:bg-foreground/90 transition-all hover:scale-[0.98] w-fit"
              @click="router.push('/chat')"
            >
              开始对话
              <ArrowRight class="h-3.5 w-3.5" />
            </button>
          </div>
          <aside class="lg:col-span-2 lg:border-l lg:border-border lg:pl-10 flex flex-col justify-center">
            <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-3">能力范围</p>
            <ul class="space-y-1.5 font-mono text-xs text-muted-foreground/80">
              <li class="flex items-center gap-2"><Microscope class="h-3.5 w-3.5 shrink-0" />问题分析<span class="text-muted-foreground/40">→</span>识别类型与边界</li>
              <li class="flex items-center gap-2"><Blocks class="h-3.5 w-3.5 shrink-0" />模型构建<span class="text-muted-foreground/40">→</span>选择最优方法</li>
              <li class="flex items-center gap-2"><Terminal class="h-3.5 w-3.5 shrink-0" />求解计算<span class="text-muted-foreground/40">→</span>Python 实时执行</li>
              <li class="flex items-center gap-2"><ShieldCheck class="h-3.5 w-3.5 shrink-0" />验证分析<span class="text-muted-foreground/40">→</span>灵敏度与鲁棒性</li>
              <li class="flex items-center gap-2"><PenLine class="h-3.5 w-3.5 shrink-0" />论文写作<span class="text-muted-foreground/40">→</span>结构化输出论文</li>
            </ul>
          </aside>
        </div>

        <!-- 方案 + 知识库 — 副入口，左右两卡 -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <button
            class="group flex items-start gap-4 rounded-lg border border-border bg-card p-5 text-left transition-all hover:border-primary/30 hover:shadow-sm"
            @click="router.push('/solution')"
          >
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted group-hover:bg-primary/10 transition-colors">
              <FileText class="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
            <div>
              <span class="font-display text-base font-medium">方案模式</span>
              <p class="text-xs text-muted-foreground mt-1 leading-relaxed">结构化输出完整建模方案，含代码与论文导出</p>
            </div>
          </button>
          <button
            class="group flex items-start gap-4 rounded-lg border border-border bg-card p-5 text-left transition-all hover:border-primary/30 hover:shadow-sm"
            @click="router.push('/knowledge')"
          >
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted group-hover:bg-primary/10 transition-colors">
              <Library class="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
            </div>
            <div>
              <span class="font-display text-base font-medium">知识库</span>
              <p class="text-xs text-muted-foreground mt-1 leading-relaxed">方法卡片 · 真题论文 · 模板套路，支持检索与导入</p>
            </div>
          </button>
        </div>
      </section>

      <!-- ·2 学习中心 -->
      <section class="pb-20">
        <div class="section-rule mb-10">
          <span class="font-mono text-xs tracking-wider">·2 &nbsp; 学习中心</span>
        </div>

        <!-- 继续学习(AI 推荐,有学习画像时显示) -->
        <div v-if="profileStore.hasProfile" class="mb-8">
          <NextRecommendationCard :role="learningStore.currentRole" compact @go="(id: string) => router.push(`/learn/${id}`)" />
        </div>

        <!-- 三角色入门 -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-12">
          <!-- 建模手 -->
          <div class="lg:col-span-4 rounded-lg border border-border bg-card p-6 hover:border-primary/20 transition-colors cursor-pointer" @click="router.push('/learn')">
            <div class="flex items-center gap-2 mb-3">
              <Blocks class="h-5 w-5 text-muted-foreground" />
              <span class="font-display font-medium">建模手</span>
              <span class="font-mono text-[10px] text-muted-foreground ml-auto">方法 + 理论</span>
            </div>
            <p class="text-sm text-muted-foreground leading-relaxed mb-4">学模型方法、练问题分析、掌握从优化到评价的完整建模工具箱</p>
            <div class="flex flex-wrap gap-1.5">
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">线性规划</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">AHP</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">TOPSIS</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">+7</span>
            </div>
          </div>
          <!-- 编程手 -->
          <div class="lg:col-span-4 rounded-lg border border-border bg-card p-6 hover:border-primary/20 transition-colors cursor-pointer" @click="router.push('/learn')">
            <div class="flex items-center gap-2 mb-3">
              <Terminal class="h-5 w-5 text-muted-foreground" />
              <span class="font-display font-medium">编程手</span>
              <span class="font-mono text-[10px] text-muted-foreground ml-auto">代码 + 数据</span>
            </div>
            <p class="text-sm text-muted-foreground leading-relaxed mb-4">Python 科学计算、算法实现、数据处理与可视化，把模型变成可运行的代码</p>
            <div class="flex flex-wrap gap-1.5">
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">NumPy</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">SciPy</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">Pandas</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">Matplotlib</span>
            </div>
          </div>
          <!-- 论文手 -->
          <div class="lg:col-span-4 rounded-lg border border-border bg-card p-6 hover:border-primary/20 transition-colors cursor-pointer" @click="router.push('/learn')">
            <div class="flex items-center gap-2 mb-3">
              <PenLine class="h-5 w-5 text-muted-foreground" />
              <span class="font-display font-medium">论文手</span>
              <span class="font-mono text-[10px] text-muted-foreground ml-auto">写作 + 排版</span>
            </div>
            <p class="text-sm text-muted-foreground leading-relaxed mb-4">学术写作规范、图表设计、LaTeX 排版，让你的模型被读懂、被认可</p>
            <div class="flex flex-wrap gap-1.5">
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">摘要撰写</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">可视化</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">LaTeX</span>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">排版</span>
            </div>
          </div>
        </div>

        <!-- 学习入口四卡 -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <button
            v-for="mod in learnModules"
            :key="mod.path"
            class="group flex flex-col items-start gap-1.5 rounded-md border border-border/60 bg-background p-4 text-left transition-all hover:border-primary/30 hover:bg-accent/30"
            @click="router.push(mod.path)"
          >
            <component :is="mod.icon" class="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
            <span class="text-sm font-medium">{{ mod.label }}</span>
            <span class="text-[11px] text-muted-foreground leading-relaxed">{{ mod.desc }}</span>
          </button>
        </div>
      </section>

      <!-- ·3 知识库 -->
      <section class="pb-20">
        <div class="section-rule mb-10">
          <span class="font-mono text-xs tracking-wider">·3 &nbsp; 知识库</span>
        </div>
        <!-- 加载中骨架(消除静默缺失) -->
        <div v-if="!statsReady && !statsFailed" class="grid grid-cols-3 gap-8">
          <div v-for="i in 3" :key="i" class="space-y-2.5">
            <Skeleton class="h-9 w-16" />
            <Skeleton class="h-3 w-24" />
          </div>
        </div>
        <!-- 失败: 弱化一行,不误导 -->
        <p v-else-if="statsFailed" class="font-mono text-xs text-muted-foreground/60">知识库统计暂不可用</p>
        <!-- 数据 -->
        <div v-else class="grid grid-cols-3 gap-8">
          <div v-for="s in statItems" :key="s.key">
            <p class="font-mono text-4xl sm:text-5xl font-medium tabular-nums leading-none">{{ s.value }}</p>
            <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground mt-3">{{ s.label }}</p>
          </div>
        </div>
      </section>

      <!-- 脚注 -->
      <footer class="border-t border-border py-10 mb-8">
        <p class="font-mono text-xs text-muted-foreground/80 leading-relaxed max-w-2xl">
          <span class="text-primary">†</span> &nbsp;
          当前为本地游客模式,对话与任务保存在本机。如需云端同步或多端协作,可在右上角设置中配置。
        </p>
      </footer>

    </div>
  </div>
</template>

<script setup lang="ts">
import { getKBStats } from "@/apis/knowledgeApi";
import NextRecommendationCard from "@/components/learning/NextRecommendationCard.vue";
import { Skeleton } from "@/components/ui/skeleton";
import { useGuidedTour } from "@/composables/useGuidedTour";
import { useLearningStore } from "@/stores/learning";
import { useProfileStore } from "@/stores/profile";
import { useTourStore } from "@/stores/tour";
import request from "@/utils/request";
import {
  ArrowRight,
  Blocks,
  BookOpen,
  CheckCircle2,
  Dumbbell,
  FileText,
  Key,
  Library,
  Loader2,
  MessageSquare,
  Microscope,
  PenLine,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  TrendingUp,
  X,
  Zap,
} from "lucide-vue-next";
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

const router = useRouter();
const route = useRoute();
const profileStore = useProfileStore();
const learningStore = useLearningStore();
const tourStore = useTourStore();
const guidedTour = useGuidedTour();

const deniedMessage = ref("");
watch(
  () => route.query.denied,
  (val) => {
    if (val === "knowledge")
      deniedMessage.value =
        "知识库仅对项目贡献者开放。请联系 zhang66633 或 shu639 获取权限。";
  },
  { immediate: true },
);
function dismissDenied() {
  deniedMessage.value = "";
  router.replace({ query: {} });
}

const myKey = ref<{
  has_key: boolean;
  key: { masked_key: string; provider: string; model_name: string } | null;
}>({ has_key: false, key: null });
const keyInput = ref("");
const activating = ref(false);
const activateError = ref("");
const showKeyInput = ref(false);

async function checkMyKey() {
  try {
    const r = await request.get<{
      has_key: boolean;
      key: { masked_key: string; provider: string; model_name: string } | null;
    }>("/apikeys/mine");
    myKey.value = r.data || { has_key: false, key: null };
    showKeyInput.value = !myKey.value.has_key;
  } catch {
    myKey.value = { has_key: false, key: null };
    showKeyInput.value = true;
  }
}

async function activateKey() {
  if (!keyInput.value.trim() || activating.value) return;
  activating.value = true;
  activateError.value = "";
  try {
    await request.post("/apikeys/quick", { key: keyInput.value.trim() });
    keyInput.value = "";
    await checkMyKey();
  } catch (e) {
    const err = e as {
      response?: { data?: { detail?: string } };
      message?: string;
    };
    activateError.value =
      err?.response?.data?.detail ||
      err?.message ||
      "激活失败，请检查 Key 是否正确";
  } finally {
    activating.value = false;
  }
}

const statsReady = ref(false);
const statsFailed = ref(false);

const learnModules = [
  {
    label: "学习工位",
    desc: "技能树导航，智能体对话式教学",
    path: "/learn",
    icon: BookOpen,
  },
  {
    label: "训练场",
    desc: "每日推荐练习，智能体出题批改",
    path: "/practice",
    icon: Dumbbell,
  },
  {
    label: "成长档案",
    desc: "学习日历、成就系统与进度追踪",
    path: "/progress",
    icon: TrendingUp,
  },
];

const statItems = ref([
  { key: "methods", label: "方法卡片", value: 0 },
  { key: "papers", label: "真题论文", value: 0 },
  { key: "templates", label: "模板套路", value: 0 },
]);

onMounted(async () => {
  // 新手首次访问: 稍候页面渲染稳定后自动启动功能导览(完成/跳过一次即不再弹)
  if (tourStore.shouldAutoStart) {
    window.setTimeout(() => guidedTour.start(), 800);
  }

  // 画像(继续学习卡;失败静默降级)
  profileStore.checkProfile();
  try {
    const res = await getKBStats();
    const data = res.data;
    statItems.value = [
      { key: "methods", label: "方法卡片", value: data.methods_count },
      { key: "papers", label: "真题论文", value: data.papers_count },
      { key: "templates", label: "模板套路", value: data.templates_count },
    ];
    statsReady.value = true;
  } catch {
    statsReady.value = false;
    statsFailed.value = true;
  }
  await checkMyKey();
});
</script>
