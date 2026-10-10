<template>
  <ChatPanel ref="chatPanel" storage-key="practice-ai" :default-width="320" button-label="刷题助手">
    <template #main>
    <!-- 主区 -->
    <div class="flex h-full flex-col min-w-0">
      <!-- 顶部 -->
      <div class="flex items-center justify-between border-b px-6 py-3 shrink-0">
        <div class="flex items-center gap-3">
          <span class="font-display text-lg font-medium">训练场</span>
          <span class="font-mono text-[10px] text-muted-foreground">· 选择题题库</span>
        </div>
        <!-- 统计条(力扣风格) -->
        <div v-if="!inSession && !sessionDone" class="flex items-center gap-4 font-mono text-[11px] text-muted-foreground">
          <span>总题数 <strong class="text-foreground">{{ bankTotal }}</strong></span>
          <span>未做 <strong class="text-foreground">{{ statusCounts.untried }}</strong></span>
          <span>错题 <strong class="text-red-500">{{ statusCounts.wrong }}</strong></span>
          <span>已掌握 <strong class="text-emerald-500">{{ statusCounts.mastered }}</strong></span>
        </div>
      </div>

      <!-- Tab 切换 -->
      <div v-if="!inSession && !sessionDone" class="flex items-center gap-6 border-b px-6 shrink-0" data-tour="practice-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          class="relative py-3 text-sm transition-colors"
          :class="activeTab === tab.value ? 'text-foreground font-medium' : 'text-muted-foreground hover:text-foreground'"
          @click="switchTab(tab.value)"
        >
          {{ tab.label }}
          <span v-if="activeTab === tab.value" class="absolute left-0 right-0 -bottom-px h-px bg-primary" />
        </button>
      </div>

      <!-- ══════ 题库浏览视图 ══════ -->
      <div v-if="!inSession && !sessionDone && activeTab === 'bank'" class="flex-1 flex flex-col min-h-0">
        <!-- 筛选栏 -->
        <div class="flex items-center gap-2 border-b px-6 py-2.5 shrink-0 flex-wrap">
          <select v-model="store.filterRole" class="rounded-md border border-border bg-background px-2.5 py-1.5 text-xs">
            <option value="">全部角色</option>
            <option value="modeler">建模手</option>
            <option value="programmer">编程手</option>
            <option value="writer">论文手</option>
          </select>
          <select v-model="store.filterCategory" class="rounded-md border border-border bg-background px-2.5 py-1.5 text-xs">
            <option value="">全部类别</option>
            <option v-for="c in store.categories" :key="c.name" :value="c.name">
              {{ c.name }}({{ c.count }})
            </option>
          </select>
          <select v-model="store.filterDifficulty" class="rounded-md border border-border bg-background px-2.5 py-1.5 text-xs">
            <option value="">全部难度</option>
            <option value="beginner">入门</option>
            <option value="intermediate">进阶</option>
            <option value="advanced">实战</option>
          </select>
          <select v-model="store.filterStatus" class="rounded-md border border-border bg-background px-2.5 py-1.5 text-xs">
            <option value="">全部状态</option>
            <option value="untried">未做</option>
            <option value="wrong">做错</option>
            <option value="mastered">已掌握</option>
          </select>
          <input
            v-model="store.searchText"
            type="text"
            placeholder="搜索题目 / 标签…"
            class="ml-auto w-48 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs outline-none focus:border-primary/50"
          />
        </div>

        <!-- 题目列表(力扣紧凑表格) -->
        <div class="flex-1 overflow-y-auto min-h-0">
          <div v-if="store.bankLoading" class="space-y-2 p-4">
            <Skeleton v-for="i in 8" :key="i" class="h-8" :class="i % 3 === 0 ? 'w-11/12' : 'w-full'" />
          </div>
          <div v-else-if="store.bankError" class="flex flex-col items-center justify-center py-20 text-sm text-muted-foreground gap-2">
            <AlertTriangle class="h-8 w-8 text-amber-500" />
            <span>{{ store.bankError }}</span>
            <button
              class="mt-1 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent transition-colors"
              @click="store.loadBank()"
            >
              重试
            </button>
          </div>
          <div v-else-if="filteredBank.length === 0" class="flex flex-col items-center justify-center py-20 text-sm text-muted-foreground gap-2">
            <Inbox class="h-8 w-8" />
            <span>暂无符合条件的题目</span>
            <span class="text-xs">试试调整筛选条件</span>
          </div>
          <table v-else class="w-full text-sm">
            <thead class="sticky top-0 bg-background z-10">
              <tr class="border-b text-left text-xs text-muted-foreground">
                <th class="w-10 px-3 py-2">
                  <input type="checkbox" :checked="allSelected" @change="store.selectAll()" class="accent-primary" />
                </th>
                <th class="w-10 px-2 py-2">状态</th>
                <th class="w-14 px-2 py-2">题号</th>
                <th class="px-2 py-2">题目</th>
                <th class="w-24 px-2 py-2">类别</th>
                <th class="w-20 px-2 py-2">难度</th>
                <th class="w-16 px-2 py-2 text-right">错次</th>
                <th class="w-20 px-2 py-2 text-right">错题本</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="q in filteredBank"
                :key="q.id"
                class="border-b border-border/50 transition-colors hover:bg-accent/50 cursor-pointer"
                @click="store.toggleSelect(q.id)"
              >
                <td class="px-3 py-2" @click.stop>
                  <input type="checkbox" :checked="store.selectedIds.has(q.id)" @change="store.toggleSelect(q.id)" class="accent-primary" />
                </td>
                <td class="px-2 py-2 text-center">
                  <Check v-if="q.status === 'mastered'" class="h-4 w-4 mx-auto text-emerald-500" title="已掌握" />
                  <X v-else-if="q.status === 'wrong'" class="h-4 w-4 mx-auto text-red-500" title="做错" />
                  <span v-else class="text-muted-foreground/40">—</span>
                </td>
                <td class="px-2 py-2 font-mono text-xs text-muted-foreground">{{ q.no }}</td>
                <td class="px-2 py-2">
                  <div
                    class="truncate text-xs prose prose-sm prose-gray dark:prose-invert max-w-none [&>p]:m-0"
                    v-html="renderMarkdown(q.question)"
                  />
                  <div class="mt-0.5 flex gap-1 flex-wrap">
                    <span v-for="t in q.tags.slice(0, 3)" :key="t" class="rounded bg-muted px-1 py-px text-[10px] text-muted-foreground">{{ t }}</span>
                  </div>
                </td>
                <td class="px-2 py-2 text-xs text-muted-foreground">{{ q.category }}</td>
                <td class="px-2 py-2">
                  <span class="rounded px-1.5 py-px text-[10px] font-medium" :class="diffBadgeClass(q.difficulty)">
                    {{ diffLabel(q.difficulty) }}
                  </span>
                </td>
                <td class="px-2 py-2 text-right font-mono text-xs" :class="q.wrong_times > 0 ? 'text-red-500' : 'text-muted-foreground/40'">
                  {{ q.wrong_times || "—" }}
                </td>
                <td class="px-2 py-2 text-right" @click.stop>
                  <button
                    class="rounded border px-1.5 py-0.5 text-[10px] transition-colors"
                    :class="q.status === 'wrong'
                      ? 'border-red-500/40 text-red-500 hover:bg-red-500/10'
                      : 'border-border text-muted-foreground hover:bg-accent'"
                    :title="q.status === 'wrong' ? '移出错题本' : '加入错题本(标记想重点复习)'"
                    @click="store.toggleMistake(q)"
                  >
                    {{ q.status === "wrong" ? "已加入" : "＋错题本" }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 底部操作条 -->
        <div class="flex items-center gap-3 border-t px-6 py-3 shrink-0">
          <span class="text-xs text-muted-foreground">已选 <strong class="text-foreground">{{ store.selectedIds.size }}</strong> 题</span>
          <label class="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
            <input v-model="store.shuffled" type="checkbox" class="accent-primary" />
            乱序
          </label>
          <button
            :disabled="store.selectedIds.size === 0"
            class="ml-auto inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            @click="beginPractice"
          >
            开始刷题({{ store.selectedIds.size }})
          </button>
        </div>
      </div>

      <!-- ══════ 错题本视图 ══════ -->
      <div v-else-if="!inSession && !sessionDone && activeTab === 'mistakes'" class="flex-1 overflow-y-auto min-h-0">
        <div v-if="store.mistakesLoading" class="space-y-2 p-4">
          <Skeleton v-for="i in 6" :key="i" class="h-8" :class="i % 3 === 0 ? 'w-11/12' : 'w-full'" />
        </div>
        <div v-else-if="mistakes.length === 0" class="flex flex-col items-center justify-center py-20 gap-2 text-muted-foreground">
          <PartyPopper class="h-8 w-8" />
          <span class="text-sm">错题本已清空</span>
          <span class="text-xs">做错的题会出现在这里,重做正确后自动移除</span>
        </div>
        <table v-else class="w-full text-sm">
          <thead class="sticky top-0 bg-background z-10">
            <tr class="border-b text-left text-xs text-muted-foreground">
              <th class="w-14 px-3 py-2">题号</th>
              <th class="px-2 py-2">题目</th>
              <th class="w-24 px-2 py-2">类别</th>
              <th class="w-20 px-2 py-2">难度</th>
              <th class="w-16 px-2 py-2 text-right">错次</th>
              <th class="w-20 px-2 py-2"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in mistakes" :key="q.id" class="border-b border-border/50 hover:bg-accent/50">
              <td class="px-3 py-2 font-mono text-xs text-muted-foreground">{{ q.no }}</td>
              <td class="px-2 py-2">
                <div
                  class="truncate text-xs prose prose-sm prose-gray dark:prose-invert max-w-none [&>p]:m-0"
                  v-html="renderMarkdown(q.question)"
                />
              </td>
              <td class="px-2 py-2 text-xs text-muted-foreground">{{ q.category }}</td>
              <td class="px-2 py-2">
                <span class="rounded px-1.5 py-px text-[10px] font-medium" :class="diffBadgeClass(q.difficulty)">
                  {{ diffLabel(q.difficulty) }}
                </span>
              </td>
              <td class="px-2 py-2 text-right font-mono text-xs text-red-500">{{ q.wrong_times }}</td>
              <td class="px-2 py-2 text-right whitespace-nowrap">
                <button class="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-accent transition-colors" @click="redoMistake(q)">
                  重做
                </button>
                <button class="ml-1.5 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent transition-colors" title="不重做,直接移出错题本" @click="store.removeMistake(q)">
                  移除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- ══════ 答题视图 ══════ -->
      <div v-else-if="inSession" class="flex-1 overflow-y-auto min-h-0">
        <div class="mx-auto max-w-3xl px-6 py-6">
          <!-- 进度 -->
          <div class="mb-4 flex items-center justify-between text-xs text-muted-foreground">
            <span class="font-mono">第 {{ store.sessionIndex + 1 }} / {{ store.session.length }} 题</span>
            <div class="flex items-center gap-4">
              <span class="font-mono flex items-center gap-1"><Check class="h-3.5 w-3.5 text-emerald-500" />{{ store.correctCount }} <X class="h-3.5 w-3.5 ml-2 text-red-500" />{{ store.answers.length - store.correctCount }}</span>
              <button
                class="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent transition-colors"
                title="半路退出: 本次作答不保存"
                @click="confirmExit = true"
              >
                <LogOut class="h-3.5 w-3.5" />退出
              </button>
            </div>
          </div>
          <div class="mb-6 h-1 rounded-full bg-muted">
            <div class="h-full rounded-full bg-primary transition-all duration-300" :style="{ width: `${((store.sessionIndex + (reveal ? 1 : 0)) / store.session.length) * 100}%` }" />
          </div>

          <template v-if="currentQuestion">
            <!-- 题面 -->
            <div class="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
              <span class="font-mono">#{{ currentQuestion.no }}</span>
              <span>{{ currentQuestion.category }}</span>
              <span class="rounded px-1.5 py-px text-[10px] font-medium" :class="diffBadgeClass(currentQuestion.difficulty)">
                {{ diffLabel(currentQuestion.difficulty) }}
              </span>
              <span v-if="currentQuestion.unit_id" class="font-mono text-[10px] opacity-60">{{ currentQuestion.unit_id }}</span>
            </div>
            <div class="prose prose-sm prose-gray dark:prose-invert max-w-none mb-5" v-html="renderMarkdown(currentQuestion.question)" />

            <!-- 选项(点击即判) -->
            <GuidedCardSelection
              v-model="chosenIndex"
              mode="quiz"
              :options="optionItems"
              :disabled="!!reveal"
              :reveal="reveal"
              @confirm="onAnswer"
            />

            <!-- 判分横幅 + 解析 -->
            <div v-if="reveal" class="mt-5 space-y-3">
              <div
                class="flex items-center gap-2 rounded-md border px-4 py-2.5 text-sm font-medium"
                :class="reveal.chosenIndex === reveal.answerIndex
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                  : 'border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-400'"
              >
                <Check v-if="reveal.chosenIndex === reveal.answerIndex" class="h-4 w-4 shrink-0" />
                <X v-else class="h-4 w-4 shrink-0" />
                <span>{{ reveal.chosenIndex === reveal.answerIndex ? "回答正确" : "回答错误" }}</span>
                <span v-if="reveal.chosenIndex !== reveal.answerIndex" class="font-normal text-muted-foreground">
                  正确答案:{{ letters[reveal.answerIndex] }}
                </span>
              </div>
              <div class="rounded-md border border-border bg-card p-4">
                <p class="mb-2 text-xs font-medium text-muted-foreground flex items-center gap-1"><BookOpen class="h-3.5 w-3.5" />解析</p>
                <div class="prose prose-sm prose-gray dark:prose-invert max-w-none" v-html="renderMarkdown(lastExplanation)" />
              </div>
              <div class="flex items-center gap-2">
                <button
                  v-if="store.sessionIndex < store.session.length - 1"
                  class="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 transition-all"
                  @click="next"
                >
                  下一题
                </button>
                <button
                  v-else
                  class="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 transition-all"
                  @click="finish"
                >
                  查看结果
                </button>
                <button
                  class="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-xs text-muted-foreground hover:bg-accent transition-colors"
                  @click="askAI"
                >
                  <Bot class="h-3.5 w-3.5" />问 AI 为什么
                </button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- ══════ 结算视图 ══════ -->
      <div v-else-if="sessionDone" class="flex-1 overflow-y-auto min-h-0">
        <div class="mx-auto max-w-3xl px-6 py-8">
          <div class="mb-6 flex items-center gap-6 rounded-md border border-border bg-card p-5">
            <div class="text-center">
              <p class="text-3xl font-display font-medium">{{ store.accuracy }}%</p>
              <p class="mt-1 text-xs text-muted-foreground">正确率</p>
            </div>
            <div class="text-center">
              <p class="text-3xl font-display font-medium">{{ store.correctCount }}/{{ store.answers.length }}</p>
              <p class="mt-1 text-xs text-muted-foreground">答对题数</p>
            </div>
            <div class="text-center">
              <p class="text-3xl font-display font-medium">{{ elapsed }}</p>
              <p class="mt-1 text-xs text-muted-foreground">用时</p>
            </div>
          </div>

          <p class="mb-3 font-display text-base font-medium">本次作答记录</p>
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b text-left text-xs text-muted-foreground">
                <th class="w-14 px-2 py-2">题号</th>
                <th class="px-2 py-2">题目</th>
                <th class="w-20 px-2 py-2">状态</th>
                <th class="w-24 px-2 py-2">类别</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in store.answers" :key="a.question.id" class="border-b border-border/50">
                <td class="px-2 py-2 font-mono text-xs text-muted-foreground">{{ a.question.no }}</td>
                <td class="px-2 py-2">
                  <div
                    class="truncate text-xs prose prose-sm prose-gray dark:prose-invert max-w-none [&>p]:m-0"
                    v-html="renderMarkdown(a.question.question)"
                  />
                </td>
                <td class="px-2 py-2">
                  <span class="text-xs font-medium flex items-center gap-1" :class="a.correct ? 'text-emerald-500' : 'text-red-500'">
                    <Check v-if="a.correct" class="h-3.5 w-3.5" />
                    <X v-else class="h-3.5 w-3.5" />
                    {{ a.correct ? "正确" : `选了 ${letters[a.chosen]}` }}
                  </span>
                </td>
                <td class="px-2 py-2 text-xs text-muted-foreground">{{ a.question.category }}</td>
              </tr>
            </tbody>
          </table>

          <div class="mt-6 flex items-center gap-2">
            <button class="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 transition-all" @click="store.backToBank()">
              回题库
            </button>
            <button class="inline-flex h-9 items-center rounded-md border border-border bg-background px-4 text-sm hover:bg-accent transition-colors" @click="redoWrong">
              专练错题
            </button>
          </div>
        </div>
      </div>
    </div>

    </template>

    <!-- ══════ 侧边 AI 面板(可缩放收起) ══════ -->
    <ChatArea
      :messages="chatSession.activePracticeMessages"
      :is-running="chatSession.getIsRunning('practice')"
      empty-text="刷题助手"
      empty-subtext="答错后点「问 AI 为什么」,把题目带进来问"
      input-placeholder="针对当前题目提问…"
      :session-title="chatSession.activePracticeSession?.title"
      cancellable
      @send="handleSend"
      @cancel="cancelStream"
      @retry="retryLast"
      @clear="chatSession.clearSession('practice')"
      @new-session="chatSession.newSession('practice')"
    />

    <!-- 退出确认弹层 -->
    <Teleport to="body">
      <div v-if="confirmExit" class="fixed inset-0 z-50 flex items-center justify-center bg-black/30" @mousedown.self="confirmExit = false">
        <div class="w-full max-w-sm rounded-lg border border-border bg-card p-5 shadow-xl">
          <p class="mb-2 font-display text-sm font-medium flex items-center gap-1.5"><LogOut class="h-4 w-4" />退出本轮练习?</p>
          <p class="mb-4 text-xs leading-relaxed text-muted-foreground">
            已答的 {{ store.answers.length }} 道题记录将全部丢弃(错题本、错次、状态不留痕迹),确定退出吗?
          </p>
          <div class="flex justify-end gap-2">
            <button class="rounded-md border border-border px-3.5 py-1.5 text-xs hover:bg-accent transition-colors" @click="confirmExit = false">
              继续刷题
            </button>
            <button class="rounded-md bg-destructive px-3.5 py-1.5 text-xs font-medium text-destructive-foreground hover:opacity-90 transition-all" @click="doExit">
              退出并丢弃
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </ChatPanel>
</template>

<script setup lang="ts">
import ChatArea from "@/components/ChatArea.vue";
import GuidedCardSelection from "@/components/GuidedCardSelection.vue";
// biome-ignore lint/style/useImportType: Vue 组件注册需要值导入,type-only 会导致运行期组件解析失败
import ChatPanel from "@/components/chat/ChatPanel.vue";
import { Skeleton } from "@/components/ui/skeleton";
import { useStreamChat } from "@/composables/useStreamChat";
import { useChatSessionStore } from "@/stores/chatSession";
import { usePracticeStore } from "@/stores/practice";
import { renderMarkdown } from "@/utils/markdown";
import {
  AlertTriangle,
  BookOpen,
  Bot,
  Check,
  Inbox,
  LogOut,
  PartyPopper,
  X,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

const store = usePracticeStore();
const chatSession = useChatSessionStore();
const chatPanel = ref<InstanceType<typeof ChatPanel>>();
// 会话存 practice 模式,后端请求走 learning 模式(含出题/教学提示词,合法 mode)
const { handleUserSend, cancelStream, retryLast } = useStreamChat(
  "practice",
  "learning",
);

const tabs = [
  { label: "题库", value: "bank" },
  { label: "错题本", value: "mistakes" },
];
const activeTab = ref("bank");
const letters = ["A", "B", "C", "D"];

const chosenIndex = ref<number | null>(null);
const reveal = ref<{ answerIndex: number; chosenIndex: number } | null>(null);
const lastExplanation = ref("");
const confirmExit = ref(false);

async function doExit() {
  confirmExit.value = false;
  chosenIndex.value = null;
  reveal.value = null;
  await store.quitSession();
}

const inSession = computed(
  () => store.session.length > 0 && !store.sessionDone,
);
const sessionDone = computed(() => store.sessionDone);
const currentQuestion = computed(() => store.currentQuestion);
const statusCounts = computed(() => store.statusCounts);
const bankTotal = computed(() => store.bankTotal);
const filteredBank = computed(() => store.filteredBank);
const optionItems = computed(() =>
  (currentQuestion.value?.options ?? []).map((label) => ({ label })),
);
const allSelected = computed(
  () =>
    store.filteredBank.length > 0 &&
    store.filteredBank.every((q) => store.selectedIds.has(q.id)),
);
const mistakes = computed(() => store.mistakes);
const elapsed = computed(() => {
  if (!store.answers.length) return "0:00";
  const secs = Math.max(
    0,
    Math.round((Date.now() - store.sessionStartAt) / 1000),
  );
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
});

function diffLabel(d: string) {
  return d === "beginner" ? "入门" : d === "intermediate" ? "进阶" : "实战";
}
function diffBadgeClass(d: string) {
  return d === "beginner"
    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
    : d === "intermediate"
      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
      : "bg-red-500/10 text-red-600 dark:text-red-400";
}

function switchTab(v: string) {
  activeTab.value = v;
  if (v === "mistakes") store.loadMistakes();
}

async function beginPractice() {
  const ids = store.filteredBank
    .filter((q) => store.selectedIds.has(q.id))
    .map((q) => q.id);
  if (!ids.length) return;
  chosenIndex.value = null;
  reveal.value = null;
  await store.startSession(ids);
}

async function onAnswer(index: number) {
  if (reveal.value) return;
  const rec = await store.answerQuestion(index);
  if (!rec) return;
  reveal.value = { answerIndex: rec.answer_index, chosenIndex: index };
  lastExplanation.value = rec.explanation;
}

function next() {
  chosenIndex.value = null;
  reveal.value = null;
  store.nextQuestion();
}

function finish() {
  store.nextQuestion(); // 最后一题 → 置 sessionDone
}

function redoMistake(q: { id: string }) {
  chosenIndex.value = null;
  reveal.value = null;
  store.startSession([q.id]);
}

function redoWrong() {
  const wrong = store.answers
    .filter((a) => !a.correct)
    .map((a) => a.question.id);
  store.backToBank();
  if (wrong.length) store.startSession(wrong);
  else switchTab("mistakes");
}

function askAI() {
  // 面板收起时自动展开
  if (chatPanel.value && !chatPanel.value.open) chatPanel.value.expand();
  const q = currentQuestion.value;
  const r = reveal.value;
  if (!q) return;
  const lines = [
    "我在训练场做到这道题:",
    q.question,
    `选项: ${q.options.map((o, i) => `${letters[i]}. ${o}`).join("  ")}`,
  ];
  if (r) {
    lines.push(
      `我选了 ${letters[r.chosenIndex]},正确答案是 ${letters[r.answerIndex]}。请讲解为什么,以及我错在哪里。`,
    );
  } else {
    lines.push("请帮我分析这道题该怎么想。");
  }
  handleUserSend(lines.join("\n"), undefined, {
    unit_type: "练习",
    title: q.unit_id,
    difficulty: q.difficulty,
    method_category: q.category,
    tags: q.tags.join(","),
    primary_agent: "verifier",
    estimated_minutes: "15",
  });
}

function handleSend(text: string) {
  const q = currentQuestion.value;
  handleUserSend(
    text,
    undefined,
    q
      ? {
          unit_type: "练习",
          title: q.unit_id,
          difficulty: q.difficulty,
          method_category: q.category,
          tags: q.tags.join(","),
          primary_agent: "verifier",
          estimated_minutes: "15",
        }
      : undefined,
  );
}

onMounted(() => {
  store.loadBank();
});
</script>
