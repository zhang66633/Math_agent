<script setup lang="ts">
import { type LearningUnit, fetchNextRecommendation } from "@/apis/learningApi";
import { Skeleton } from "@/components/ui/skeleton";
import { PartyPopper, Sparkles } from "lucide-vue-next";
import { ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    /** 角色,变化时自动重新拉取推荐 */
    role: string;
    /** 紧凑变体(学习工位侧栏用) */
    compact?: boolean;
  }>(),
  { compact: false },
);

const emit = defineEmits<{ go: [unitId: string] }>();

const recommendation = ref<LearningUnit | null>(null);
const loading = ref(true);
const error = ref("");

const difficultyLabel: Record<string, string> = {
  beginner: "入门",
  intermediate: "进阶",
  advanced: "高阶",
  competition: "竞赛",
};
const difficultyBadge: Record<string, string> = {
  beginner: "border-emerald-200 text-emerald-700 bg-emerald-50",
  intermediate: "border-amber-200 text-amber-700 bg-amber-50",
  advanced: "border-red-200 text-red-700 bg-red-50",
  competition: "border-purple-200 text-purple-700 bg-purple-50",
};

async function refresh() {
  loading.value = true;
  error.value = "";
  try {
    const res = await fetchNextRecommendation(props.role);
    recommendation.value = res.data.recommended_unit ?? null;
  } catch {
    error.value = "推荐加载失败";
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.role,
  () => refresh(),
);
refresh();

defineExpose({ refresh });
</script>

<template>
  <div class="rounded-lg border border-border bg-card">
    <!-- 加载中 -->
    <div v-if="loading" class="space-y-2 p-3">
      <Skeleton class="h-3 w-14" />
      <Skeleton class="h-4 w-3/4" />
      <Skeleton class="h-7 w-full" />
    </div>

    <!-- 失败(不影响主流程,仅显示重试) -->
    <div v-else-if="error" class="flex items-center justify-between p-3">
      <span class="text-xs text-muted-foreground">{{ error }}</span>
      <button
        class="cursor-pointer text-xs text-primary hover:underline"
        @click="refresh"
      >
        重试
      </button>
    </div>

    <!-- 推荐单元 -->
    <div v-else-if="recommendation" class="p-3">
      <p class="font-mono text-[10px] uppercase tracking-wider text-primary flex items-center gap-1">
        <Sparkles class="h-3 w-3" />AI 建议
      </p>
      <p class="mt-1.5 text-sm font-medium leading-snug">
        {{ recommendation.title }}
      </p>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <span
          class="rounded border px-1.5 py-0.5 font-mono text-[10px]"
          :class="difficultyBadge[recommendation.difficulty] ?? 'border-border text-muted-foreground'"
        >
          {{ difficultyLabel[recommendation.difficulty] ?? recommendation.difficulty }}
        </span>
        <span class="font-mono text-[10px] text-muted-foreground">
          ⏱ {{ recommendation.estimated_minutes }}分钟
        </span>
        <span class="flex-1" />
        <button
          class="cursor-pointer rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          @click="emit('go', recommendation.unit_id)"
        >
          开始学习 →
        </button>
      </div>
    </div>

    <!-- 全部完成 -->
    <p v-else class="p-3 text-xs text-muted-foreground flex items-center gap-1.5">
      <PartyPopper class="h-3.5 w-3.5 shrink-0" />本路径单元已全部完成,去训练场巩固吧
    </p>
  </div>
</template>
