<template>
  <div class="skill-graph">
    <div class="relative mb-3">
      <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索方法..."
        class="w-full rounded-md border border-border bg-background pl-9 pr-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
    </div>

    <p class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-3">
      {{ title }}
    </p>

    <div v-if="loading" class="space-y-2 py-4">
      <Skeleton v-for="i in 5" :key="i" class="h-5 w-full" />
    </div>

    <div v-else-if="error" class="text-xs text-destructive py-4">{{ error }}</div>

    <div v-else class="space-y-1">
      <div v-for="cat in filteredTree" :key="cat.name" class="mb-3">
        <button
          class="flex items-center gap-2 w-full text-left py-1.5 text-sm font-medium hover:text-foreground transition-colors"
          :class="cat.expanded ? 'text-foreground' : 'text-muted-foreground'"
          @click="cat.expanded = !cat.expanded"
        >
          <ChevronRight
            class="h-3.5 w-3.5 shrink-0 transition-transform"
            :class="{ 'rotate-90': cat.expanded }"
          />
          <span class="truncate">{{ cat.name }}</span>
        </button>
        <div v-if="cat.expanded" class="ml-4 space-y-0.5">
          <div
            v-for="unit in cat.units"
            :key="unit.id"
            class="flex items-center gap-2 py-1 px-2 rounded text-sm cursor-pointer transition-colors hover:bg-accent group"
            :class="statusClass(unit.status)"
            @click="$emit('select', unit.id)"
          >
            <component :is="statusIcon(unit.status)" class="h-3.5 w-3.5 shrink-0" :class="statusIconClass(unit.status)" />
            <span class="truncate flex-1">{{ unit.name }}</span>
            <span v-if="unit.difficulty" class="text-[9px] font-mono px-1 py-0.5 rounded shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
              :class="diffBadge(unit.difficulty)">{{ diffLabel(unit.difficulty) }}</span>
          </div>
        </div>
      </div>

      <div v-if="filteredTree.length === 0 && searchQuery" class="text-xs text-muted-foreground py-4 text-center">
        未找到匹配项
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Skeleton } from "@/components/ui/skeleton";
import {
  CheckCircle2,
  ChevronRight,
  Circle,
  RefreshCw,
  Search,
} from "lucide-vue-next";
import { computed, ref, watch } from "vue";

interface SkillUnit {
  id: string;
  name: string;
  status: "completed" | "active" | "locked";
  difficulty?: string;
}

interface SkillCategory {
  name: string;
  expanded: boolean;
  units: SkillUnit[];
}

const props = withDefaults(
  defineProps<{
    categories?: SkillCategory[];
    title?: string;
    loading?: boolean;
    error?: string;
  }>(),
  {
    categories: () => [],
    title: "技能树",
    loading: false,
    error: "",
  },
);

defineEmits<{
  select: [unitId: string];
}>();

const searchQuery = ref("");

// 用 reactive 让每个 category 的 expanded 状态独立可变
const localCategories = ref<SkillCategory[]>([]);

watch(
  () => props.categories,
  (cats) => {
    localCategories.value = cats.map((c) => ({ ...c }));
  },
  { immediate: true, deep: true },
);

const filteredTree = computed(() => {
  if (!searchQuery.value.trim()) return localCategories.value;
  const q = searchQuery.value.trim().toLowerCase();
  return localCategories.value
    .map((cat) => ({
      ...cat,
      expanded: true,
      units: cat.units.filter((u) => u.name.toLowerCase().includes(q)),
    }))
    .filter((cat) => cat.units.length > 0);
});

function statusClass(status: string) {
  return (
    {
      completed: "text-foreground",
      active: "text-primary font-medium bg-primary/5",
      locked: "text-muted-foreground",
    }[status] ?? "text-muted-foreground"
  );
}

function statusIcon(status: string) {
  if (status === "completed") return CheckCircle2;
  if (status === "active") return RefreshCw;
  return Circle;
}
function statusIconClass(status: string) {
  if (status === "completed") return "text-foreground";
  if (status === "active") return "text-primary";
  return "text-muted-foreground/40";
}
function diffLabel(d: string) {
  return (
    {
      beginner: "入门",
      intermediate: "进阶",
      advanced: "实战",
      competition: "竞赛",
    }[d] ?? ""
  );
}
function diffBadge(d: string) {
  return (
    {
      beginner: "bg-emerald-50 text-emerald-600",
      intermediate: "bg-amber-50 text-amber-600",
      advanced: "bg-purple-50 text-purple-600",
      competition: "bg-red-50 text-red-600",
    }[d] ?? ""
  );
}
</script>
