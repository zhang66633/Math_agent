<script setup lang="ts">
import ChatArea from "@/components/ChatArea.vue";
import SkillGraph from "@/components/SkillGraph.vue";
// biome-ignore lint/style/useImportType: Vue 组件注册需要值导入,type-only 会导致运行期组件解析失败
import ChatPanel from "@/components/chat/ChatPanel.vue";
import { useStreamChat } from "@/composables/useStreamChat";
import { useChatSessionStore } from "@/stores/chatSession";
import { type AgentRole, useLearningStore } from "@/stores/learning";
import { Compass, PanelLeft, PanelLeftOpen } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const treeOpen = ref(true);
const store = useLearningStore();
const chatSession = useChatSessionStore();
const hubChatPanel = ref<InstanceType<typeof ChatPanel>>();
// 聊天面板开合(组件实例暴露的 open 是响应式的),收起时显示空白区水印
const hubChatOpen = computed(() => hubChatPanel.value?.open ?? false);
const { handleUserSend, restoreLatestSession, cancelStream, retryLast } =
  useStreamChat("learning", "learning");

const roleLabel = computed(() => {
  const labels: Record<AgentRole, string> = {
    modeler: "建模手",
    programmer: "编程手",
    writer: "论文手",
  };
  return labels[store.currentRole] ?? "建模手";
});

onMounted(() => {
  store.loadPath();
  restoreLatestSession();
});

function handleUnitSelect(unitId: string) {
  router.push(`/learn/${unitId}`);
}

function handleSend(text: string) {
  handleUserSend(text);
}

// 工位聊天空态快捷提问
const hubQuickActions = [
  {
    label: "我现在该学什么",
    text: "我现在该学什么?请根据我的学习路径给我一个建议",
  },
  { label: "帮我制定学习计划", text: "帮我制定一个本周的学习计划" },
];
</script>

<template>
  <div class="flex h-full bg-background">
    <div class="flex-1 min-w-0 flex flex-col">
      <!-- 顶部状态栏 -->
      <div class="flex items-center justify-between border-b px-6 py-3 shrink-0">
        <div class="flex items-center gap-3">
          <span class="font-display text-lg font-medium">学习工位</span>
          <span class="font-mono text-[10px] text-muted-foreground">· 智能体对话式教学</span>
        </div>
        <div class="flex items-center gap-2" data-tour="learn-role">
          <span class="font-mono text-[10px] text-muted-foreground">角色</span>
          <select
            class="rounded-md border border-border bg-background px-3 py-1.5 text-sm"
            :value="store.currentRole"
            @change="store.switchRole(($event.target as HTMLSelectElement).value as AgentRole)"
          >
            <option value="modeler">建模手</option>
            <option value="programmer">编程手</option>
            <option value="writer">论文手</option>
          </select>
        </div>
      </div>

      <!-- 主内容区: 技能树 + AI 对话(面板化,返回时默认隐藏) -->
      <div class="flex-1 min-h-0">
        <ChatPanel
          ref="hubChatPanel"
          storage-key="hub-chat"
          :default-width="380"
          button-label="助手"
          :start-collapsed="true"
          class="h-full"
        >
          <template #main>
            <div class="h-full flex min-w-0">
              <!-- 左侧技能树(可折叠,折叠按钮两态固定在底部) -->
              <div
                class="h-full shrink-0 border-r flex flex-col transition-all duration-200"
                :class="treeOpen ? 'w-72' : 'w-10'"
              >
                <div v-if="treeOpen" class="flex-1 overflow-y-auto p-4 min-h-0">
                  <SkillGraph
                    :categories="store.skillTree"
                    :title="`${roleLabel}技能树`"
                    :loading="store.loading"
                    :error="store.error"
                    @select="handleUnitSelect"
                  />
                </div>
                <!-- 收起态占位,保证按钮不跳到顶部 -->
                <div v-else class="flex-1" />
                <button
                  class="flex shrink-0 items-center justify-center border-t py-2 transition-colors hover:bg-accent/50"
                  :title="treeOpen ? '折叠技能树' : '展开技能树'"
                  @click="treeOpen = !treeOpen"
                >
                  <PanelLeftOpen v-if="treeOpen" class="h-3.5 w-3.5 text-muted-foreground" />
                  <PanelLeft v-else class="h-3.5 w-3.5 text-muted-foreground" />
                </button>
              </div>

              <!-- 聊天收起时的空白区水印 -->
              <div
                v-if="!hubChatOpen"
                class="flex-1 flex flex-col items-center justify-center gap-3 select-none pointer-events-none"
              >
                <Compass class="h-12 w-12 opacity-30" stroke-width={1.5} />
                <p class="font-display text-xl text-muted-foreground/50">学习工位</p>
                <p class="text-xs leading-relaxed text-muted-foreground/35 text-center">
                  从左侧技能树选择一个知识点开始学习<br />
                  点进资料后,AI 助手会在右侧为你答疑<br />
                  点右下角「助手」随时召唤
                </p>
              </div>
            </div>
          </template>

          <!-- 智能体对话区 -->
          <ChatArea
            :messages="chatSession.activeLearningMessages"
            :is-running="chatSession.getIsRunning('learning')"
            empty-text="从左侧技能树选择一个知识点"
            empty-subtext="智能体将用对话方式为你讲解"
            input-placeholder="向智能体提问..."
            :session-title="chatSession.activeLearningSession?.title"
            :quick-actions="hubQuickActions"
            cancellable
            @send="handleSend"
            @cancel="cancelStream"
            @retry="retryLast"
            @clear="chatSession.clearSession('learning')"
            @new-session="chatSession.newSession('learning')"
          />
        </ChatPanel>
      </div>
    </div>
  </div>
</template>