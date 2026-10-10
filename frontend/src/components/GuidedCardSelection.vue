<template>
  <div class="space-y-4">
    <!-- 问题区 -->
    <div v-if="title" class="space-y-1">
      <p class="text-sm font-medium text-foreground">{{ title }}</p>
      <p v-if="description" class="text-xs text-muted-foreground">
        {{ description }}
      </p>
    </div>

    <!-- 圆角卡片选项 -->
    <div
      class="grid gap-2.5"
      :class="options.length <= 2 ? 'grid-cols-1' : 'grid-cols-2 max-sm:grid-cols-1'"
      role="radiogroup"
    >
      <button
        v-for="(opt, oi) in options"
        :key="oi"
        type="button"
        role="radio"
        :aria-checked="modelValue === oi"
        :disabled="disabled"
        :class="cardClass(oi)"
        :style="{ animationDelay: `${oi * 50}ms` }"
        @click="onCardClick(oi)"
        @dblclick="onCardDoubleClick(oi)"
      >
        <span class="flex items-start gap-2.5 min-w-0">
          <span
            v-if="lettered"
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded border font-mono text-[11px] font-bold transition-colors"
            :class="modelValue === oi && !reveal
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border bg-muted/50 text-muted-foreground'"
          >{{ letters[oi] }}</span>
          <span v-if="opt.icon" class="text-base leading-5 shrink-0">{{ opt.icon }}</span>
          <span class="min-w-0 text-left">
            <span class="block text-sm leading-5" v-html="mdInline(opt.label)" />
            <span
              v-if="opt.description"
              class="mt-0.5 block text-[11px] leading-4 opacity-60"
              v-html="mdInline(opt.description)"
            />
          </span>
        </span>
        <span
          v-if="modelValue === oi && !reveal"
          class="absolute right-2.5 top-2.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground"
        ><Check class="h-2.5 w-2.5" stroke-width="3" /></span>
        <span
          v-else-if="reveal && oi === reveal.answerIndex"
          class="absolute right-2.5 top-2.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white"
        ><Check class="h-2.5 w-2.5" stroke-width="3" /></span>
        <span
          v-else-if="reveal && oi === reveal.chosenIndex && oi !== reveal.answerIndex"
          class="absolute right-2.5 top-2.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-red-500 text-white"
        ><X class="h-2.5 w-2.5" stroke-width="3" /></span>
      </button>
    </div>

    <!-- 底部操作区(仅 guided 模式) -->
    <div v-if="mode === 'guided'" class="flex items-center gap-2 pt-1">
      <button
        type="button"
        :disabled="modelValue === null || disabled"
        class="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        @click="confirm"
      >
        下一步
        <kbd class="ml-1 rounded border border-primary-foreground/30 px-1 font-mono text-[10px] opacity-70">Enter</kbd>
      </button>
      <span v-if="modelValue === null" class="text-xs text-muted-foreground">
        请先选择一项(双击卡片可直接确认)
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { renderMarkdown } from "@/utils/markdown";
import { onBeforeUnmount, onMounted } from "vue";

/** 行内 markdown 渲染：去掉外层 <p>，供选项文本内嵌公式使用 */
function mdInline(text: string): string {
  return renderMarkdown(text)
    .replace(/^<p>/, "")
    .replace(/<\/p>$/, "");
}

export interface GuidedOption {
  label: string;
  description?: string;
  icon?: string;
}

export interface QuizReveal {
  answerIndex: number;
  chosenIndex: number;
}

const props = withDefaults(
  defineProps<{
    /** 问题标题 */
    title?: string;
    /** 问题提示语 */
    description?: string;
    options: GuidedOption[];
    /** 选中下标(null = 未选择),支持 v-model */
    modelValue?: number | null;
    /** guided: 选择后点「下一步」确认; quiz: 点击卡片立即确认 */
    mode?: "guided" | "quiz";
    /** 锁定交互(quiz 判分后) */
    disabled?: boolean;
    /** 判分结果(quiz 模式判分后着色: 正确绿/错选红) */
    reveal?: QuizReveal | null;
    /** 「下一步」按钮文案 */
    confirmText?: string;
    /** 选项前显示 A/B/C/D 字母徽章 */
    lettered?: boolean;
  }>(),
  {
    title: "",
    description: "",
    modelValue: null,
    mode: "guided",
    disabled: false,
    reveal: null,
    confirmText: "下一步",
    lettered: true,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: number | null];
  confirm: [index: number];
}>();

const letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I"];

function cardClass(oi: number): string[] {
  const base = [
    "relative rounded-xl border p-3.5 text-left transition-all duration-150 select-none",
    "animate-[fadeInUp_0.3s_ease-out_both]",
  ];
  if (props.reveal) {
    // 判分着色状态
    if (oi === props.reveal.answerIndex) {
      base.push("border-emerald-500 bg-emerald-500/10 cursor-default");
    } else if (
      oi === props.reveal.chosenIndex &&
      oi !== props.reveal.answerIndex
    ) {
      base.push("border-red-500 bg-red-500/10 cursor-default");
    } else {
      base.push("border-border bg-card opacity-50 cursor-default");
    }
    return base;
  }
  if (props.disabled) {
    base.push("border-border bg-card opacity-50 cursor-not-allowed");
    return base;
  }
  if (props.modelValue === oi) {
    // 选中高亮
    base.push(
      "border-primary bg-primary/5 shadow-sm scale-[1.01] cursor-pointer",
    );
  } else {
    base.push(
      "border-border bg-card hover:border-primary/40 hover:bg-accent hover:-translate-y-0.5 cursor-pointer",
    );
  }
  return base;
}

function select(oi: number) {
  if (props.disabled) return;
  if (props.modelValue === oi) {
    emit("update:modelValue", null); // 再次点击已选中项 = 取消
  } else {
    emit("update:modelValue", oi);
  }
}

function onCardClick(oi: number) {
  if (props.disabled) return;
  select(oi);
  if (
    props.mode === "quiz" &&
    props.modelValue !== null &&
    props.modelValue !== oi
  ) {
    // quiz 模式: 点击卡片即确认(点已选中项仅取消,不判分)
  } else if (
    props.mode === "quiz" &&
    props.modelValue === null &&
    props.modelValue !== oi
  ) {
    // 首次选择: 立即确认
    emit("confirm", oi);
  } else if (props.mode === "quiz") {
    // 已选中该项再点 = 取消(不确认)
  }
}

function onCardDoubleClick(oi: number) {
  if (props.disabled) return;
  emit("update:modelValue", oi);
  emit("confirm", oi); // 双击直接确认(guided 快捷路径)
}

function confirm() {
  if (props.modelValue === null || props.disabled) return;
  emit("confirm", props.modelValue);
}

// 键盘操作: 数字键快速选择, Enter 确认, Esc 取消
function onKeydown(e: KeyboardEvent) {
  if (props.disabled) return;
  const n = Number(e.key);
  if (Number.isInteger(n) && n >= 1 && n <= props.options.length) {
    emit("update:modelValue", n - 1);
    if (props.mode === "quiz") emit("confirm", n - 1);
    return;
  }
  if (e.key === "Enter" && props.mode === "guided") {
    confirm();
  } else if (e.key === "Escape") {
    emit("update:modelValue", null);
  }
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<style scoped>
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
