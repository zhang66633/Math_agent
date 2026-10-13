<template>
  <div class="rounded-lg border border-border bg-card overflow-hidden">
    <Collapsible v-model:open="isOpen">
      <CollapsibleTrigger as-child>
        <button
          class="w-full flex items-center justify-between px-4 py-2.5 hover:bg-accent/40 transition-colors"
        >
          <div class="flex items-center gap-2">
            <span class="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">§ 执行进度</span>
            <Badge :variant="statusBadgeVariant" class="gap-1 text-[10px]">
              <span class="h-1.5 w-1.5 rounded-full" :class="statusDotClass" />
              {{ statusLabel }}
            </Badge>
          </div>
          <ChevronDown class="h-3.5 w-3.5 text-muted-foreground transition-transform duration-200" :class="{ 'rotate-180': isOpen }" />
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div class="px-4 pb-4 pt-1">
          <ol class="relative space-y-3">
            <li v-for="(s, idx) in steps" :key="s.id" class="relative pl-9">
              <span
                v-if="idx !== steps.length - 1"
                class="absolute left-3 top-6 h-[calc(100%-0.5rem)] w-px"
                :class="s.status === 'done' ? 'bg-primary/60' : 'bg-border'"
              />
              <span
                class="absolute left-0 top-1 flex h-6 w-6 items-center justify-center rounded-full border-2 text-[10px] font-semibold"
                :class="nodeClass(s.status)"
              >
                <Loader2 v-if="s.status === 'active'" class="h-3 w-3 animate-spin" />
                <Check v-else-if="s.status === 'done'" class="h-3 w-3" />
                <Minus v-else-if="s.status === 'skipped'" class="h-3 w-3" />
                <span v-else>{{ idx + 1 }}</span>
              </span>
              <div class="flex flex-col">
                <span
                  class="text-sm font-medium"
                  :class="
                    s.status === 'wait'
                      ? 'text-muted-foreground'
                      : s.status === 'skipped'
                        ? 'text-muted-foreground/60 line-through'
                        : 'text-foreground'
                  "
                >
                  {{ s.label }}
                </span>
                <span class="text-xs text-muted-foreground">{{ s.description }}</span>
              </div>
            </li>
          </ol>

          <!-- 本题装配的技能（技能系统）：按题型自动加载的建模规范，只读展示 -->
          <div v-if="skills.length" class="mt-3 border-t border-border pt-2.5">
            <p class="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              <Sparkles class="h-3 w-3" />
              § 装配技能
              <span class="font-sans normal-case tracking-normal">（按题型自动加载）</span>
            </p>
            <div class="mt-1.5 flex flex-wrap gap-1.5">
              <Badge
                v-for="name in skills"
                :key="name"
                variant="muted"
                class="font-mono text-[10px]"
              >
                {{ name }}
              </Badge>
            </div>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  </div>
</template>

<script setup lang="ts">
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Check, ChevronDown, Loader2, Minus, Sparkles } from "lucide-vue-next";
import { computed, ref, watch } from "vue";

export interface ProgressStep {
  id: string;
  label: string;
  description: string;
  status: "wait" | "active" | "done" | "skipped";
}

const props = withDefaults(
  defineProps<{
    steps: ProgressStep[];
    open?: boolean;
    running?: boolean;
    completed?: boolean;
    wsStatus?: string;
    /** 本题装配的技能名（技能系统）；空数组时不渲染该区块 */
    skills?: string[];
  }>(),
  { open: true, running: false, completed: false, skills: () => [] },
);

const emit = defineEmits<{ toggle: [] }>();

const isOpen = ref(props.open);

watch(
  () => props.open,
  (v) => {
    isOpen.value = v;
  },
);

watch(isOpen, (v) => {
  if (v !== props.open) emit("toggle");
});

const statusLabel = computed(() => {
  if (props.completed) return "已完成";
  if (props.running) {
    const cur = props.steps.find((s) => s.status === "active");
    return cur ? `正在执行：${cur.label}` : "正在初始化";
  }
  return "空闲";
});

const statusBadgeVariant = computed(() => {
  if (props.completed) return "accent";
  if (props.running) return "default";
  return "muted";
});

const statusDotClass = computed(() => {
  if (props.completed) return "bg-accent-foreground";
  if (props.running) return "bg-primary animate-pulse";
  return "bg-muted-foreground/40";
});

function nodeClass(status: ProgressStep["status"]) {
  if (status === "active")
    return "border-primary bg-primary text-primary-foreground";
  if (status === "done")
    return "border-primary bg-primary text-primary-foreground";
  if (status === "skipped")
    return "border-border bg-muted text-muted-foreground";
  return "border-border bg-background text-muted-foreground";
}
</script>
