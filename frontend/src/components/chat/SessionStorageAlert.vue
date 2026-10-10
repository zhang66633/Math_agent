<template>
  <div
    v-if="visible"
    class="fixed top-0 left-0 right-0 z-50 flex items-center justify-center px-4 py-2 text-xs"
    :class="isDanger ? 'bg-destructive/10 text-destructive border-b border-destructive/20' : 'bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200 border-b border-amber-200 dark:border-amber-800'"
  >
    <AlertTriangle class="h-3.5 w-3.5 mr-1.5 shrink-0" />
    <span>
      {{ isDanger
        ? `本地存储即将用尽（${usagePercent}%）。旧对话可能无法保存。`
        : `本地存储空间不足（${usagePercent}%）。建议清理旧会话。` }}
    </span>
    <button
      class="ml-3 underline hover:no-underline"
      @click="handleCleanup"
    >
      {{ isDanger ? '立即清理' : '清理旧会话' }}
    </button>
    <button
      class="ml-3 text-muted-foreground hover:text-foreground"
      title="关闭"
      @click="dismissed = true"
    >
      <X class="h-3.5 w-3.5" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { AlertTriangle, X } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref } from "vue";

const STORAGE_KEY = "mma-chat-sessions";
const WARN_THRESHOLD = 0.8; // 4MB / 5MB
const DANGER_THRESHOLD = 0.9; // 4.5MB / 5MB

const storageSize = ref(0);
const dismissed = ref(false);
let timer: ReturnType<typeof setInterval> | null = null;

const MAX_SIZE = 5 * 1024 * 1024; // 5MB localStorage limit

const usagePercent = computed(() =>
  Math.round((storageSize.value / MAX_SIZE) * 100),
);
const isDanger = computed(
  () => storageSize.value > MAX_SIZE * DANGER_THRESHOLD,
);
const visible = computed(() => {
  if (dismissed.value) return false;
  return storageSize.value > MAX_SIZE * WARN_THRESHOLD;
});

function checkStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    storageSize.value = raw ? new Blob([raw]).size : 0;
  } catch {
    storageSize.value = 0;
  }
}

function handleCleanup() {
  // 删除最旧的 30% 会话
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    // 遍历所有模式，保留最新的 70%
    const modes = [
      "chatSessions",
      "solutionSessions",
      "learningSessions",
      "practiceSessions",
    ];
    for (const mode of modes) {
      if (Array.isArray(data[mode]) && data[mode].length > 3) {
        const keep = Math.max(3, Math.ceil(data[mode].length * 0.7));
        data[mode] = data[mode]
          .sort(
            (a: { updatedAt: string }, b: { updatedAt: string }) =>
              new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
          )
          .slice(0, keep);
      }
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    checkStorage();
    dismissed.value = true;
  } catch {
    // 清理失败，静默
  }
}

onMounted(() => {
  checkStorage();
  timer = setInterval(checkStorage, 30000); // 每 30 秒检查一次
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>