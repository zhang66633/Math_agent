<template>
  <div class="rounded-md border border-border bg-card p-4">
    <div class="mb-3 flex items-center justify-between">
      <p class="font-display text-base font-medium">学习日历</p>
      <span class="font-mono text-[10px] text-muted-foreground">近 12 周</span>
    </div>

    <div class="overflow-x-auto">
      <div class="grid w-max grid-flow-col grid-rows-7 gap-[3px]">
        <div
          v-for="(day, i) in calendar"
          :key="day.date"
          class="h-[13px] w-[13px] rounded-[3px] transition-transform hover:scale-125"
          :class="day.count > 0
            ? 'bg-primary/80 hover:bg-primary'
            : 'bg-muted/40'"
          :title="tooltip(day)"
          v-bind="stagger.itemProps(Math.min(i, 30))"
        />
      </div>
    </div>

    <div class="mt-3 flex items-center gap-1.5 text-[10px] text-muted-foreground">
      <span>少</span>
      <span class="h-[11px] w-[11px] rounded-[3px] bg-muted/40" />
      <span class="h-[11px] w-[11px] rounded-[3px] bg-primary/80" />
      <span>多</span>
      <span class="ml-auto font-mono">点亮每一天</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useStaggerReveal } from "@/composables/useStaggerReveal";

const props = defineProps<{
  calendar: { date: string; count: number }[];
}>();

const stagger = useStaggerReveal({ count: props.calendar.length, delay: 4 });

function tooltip(day: { date: string; count: number }): string {
  const [y, m, d] = day.date.split("-").map(Number);
  return `${y}年${m}月${d}日 · ${day.count > 0 ? "有学习活动" : "未学习"}`;
}
</script>
