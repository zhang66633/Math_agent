<!-- Knowledge page v2 — public access -->
<template>
  <div class="h-full overflow-y-auto overflow-x-hidden bg-grid-paper">
    <div class="mx-auto max-w-4xl px-6 sm:px-10 py-12 sm:py-16 overflow-x-hidden">
      <p class="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground mb-4">§4 &nbsp; 知识库</p>
      <h1 class="font-display text-3xl sm:text-4xl font-medium tracking-tight">方法卡片、真题与模板</h1>
      <p class="mt-2 text-sm text-muted-foreground">检索已有知识,管理条目,或从原始文本导入新内容。</p>

      <!-- login / contributor status -->
      <div v-if="!auth.isLoggedIn" class="mt-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-2.5 flex items-center gap-3">
        <AlertTriangle class="h-4 w-4 shrink-0 text-amber-600" />
        <span class="text-sm text-amber-800">未登录 — 无法上传或管理知识。请先登录 GitHub 账号。</span>
        <router-link to="/login" class="ml-auto text-sm text-amber-700 underline shrink-0">去登录</router-link>
      </div>
      <div v-else-if="!auth.isContributor" class="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 flex items-center gap-3">
        <XCircle class="h-4 w-4 shrink-0 text-red-600" />
        <span class="text-sm text-red-700">当前登录: <strong>{{ auth.user?.login }}</strong> — 不在贡献者列表中。</span>
        <button class="ml-auto text-sm text-red-700 underline shrink-0" @click="auth.logout(); $router.go(0)">退出重登</button>
      </div>
      <div v-else class="mt-4 rounded-md border border-green-200 bg-green-50 px-4 py-2.5 flex items-center gap-3">
        <CheckCircle2 class="h-4 w-4 shrink-0 text-green-600" />
        <span class="text-sm text-green-700">已认证为贡献者: <strong>{{ auth.user?.login }}</strong></span>
      </div>

        <!-- Tabs:章节式等宽标签 + 下划线高亮,无胶囊背景 -->
        <div class="flex items-center gap-6 border-b mt-8 mb-8" data-tour="knowledge-tabs">
          <button v-for="(tab, i) in tabs" :key="tab.value"
            class="relative flex items-center gap-2 py-3 text-sm transition-colors"
            :class="activeTab === tab.value ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'"
            @click="switchTab(tab.value)">
            <span class="font-mono text-[10px] text-muted-foreground/70">·4.{{ i + 1 }}</span>
            <span :class="activeTab === tab.value ? 'font-display font-medium' : ''">{{ tab.label }}</span>
            <span v-if="activeTab === tab.value" class="absolute left-0 right-0 -bottom-px h-px bg-primary"></span>
          </button>
        </div>

        <!-- ==================== TAB 1: 检索知识 ==================== -->
        <KnowledgeSearchPanel v-if="activeTab === 'search'" />

        <!-- ==================== TAB 2: 管理知识 ==================== -->
        <KnowledgeManagePanel v-if="activeTab === 'manage'" :is-contributor="isContributor" :initial-sub-type="manageSubType" @refresh-stats="loadStats" />

        <!-- ==================== TAB 3: 导入知识 ==================== -->
        <div v-if="activeTab === 'import'">
          <KnowledgeImportPanel @refresh-stats="loadStats" @goto-manage="goToManage" />
        </div>
      </div>
  </div>
</template>

<script setup lang="ts">
import { type KBStats, getKBStats } from "@/apis/knowledgeApi";
import KnowledgeImportPanel from "@/components/knowledge/KnowledgeImportPanel.vue";
import KnowledgeManagePanel from "@/components/knowledge/KnowledgeManagePanel.vue";
import KnowledgeSearchPanel from "@/components/knowledge/KnowledgeSearchPanel.vue";
import { useAuthStore } from "@/stores/auth";
import {
  AlertTriangle,
  CheckCircle2,
  Layers,
  Search,
  Upload,
  XCircle,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

// ── auth ─────────────────────────────────────────────────────────
const router = useRouter();
const auth = useAuthStore();
const isContributor = computed(() => auth.isContributor);
const authReady = computed(() => auth.authReady);

// ── tabs ─────────────────────────────────────────────────────────
const tabs = [
  { value: "search", label: "检索知识", icon: Search },
  { value: "manage", label: "管理知识", icon: Layers },
  { value: "import", label: "导入知识", icon: Upload },
];
const activeTab = ref("search");
// 管理知识面板要打开的子页签(导入成功后跳转用: method/paper/template/problem)
const manageSubType = ref("method");

function switchTab(v: string) {
  // 手动进入管理知识时回到默认子页签(只有导入成功跳转才指定子页签)
  if (v === "manage") manageSubType.value = "method";
  activeTab.value = v;
}

function goToManage(subType: string) {
  manageSubType.value = subType || "method";
  activeTab.value = "manage";
}

// ── shared ──────────────────────────────────────────────────────
const stats = ref<KBStats>({
  methods_count: 0,
  papers_count: 0,
  templates_count: 0,
  problems_count: 0,
  total: 0,
});
async function loadStats() {
  try {
    const r = await getKBStats();
    stats.value = r.data;
  } catch {
    /*ignore*/
  }
}
onMounted(async () => {
  if (auth.token && !auth.user) await auth.checkSession();
  loadStats();
});
</script>
