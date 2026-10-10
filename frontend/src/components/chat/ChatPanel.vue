<template>
  <div class="relative flex h-full min-h-0">
    <!-- 主内容区 -->
    <div class="min-h-0 min-w-0 flex-1">
      <slot name="main" />
    </div>

    <!-- 拖拽分隔条 -->
    <div
      v-if="open"
      class="group relative w-1.5 shrink-0 cursor-col-resize transition-colors hover:bg-primary/30 active:bg-primary/50"
      @mousedown="startResize"
    >
      <div class="absolute inset-y-0 -left-1 -right-1" />
    </div>

    <!-- 聊天面板 -->
    <div
      v-show="open"
      class="flex min-h-0 shrink-0 flex-col overflow-hidden border-l"
      :style="{ width: width + 'px' }"
    >
      <div class="min-h-0 flex-1">
        <slot />
      </div>
      <!-- 底部收起条(与左侧侧栏折叠按钮一致的底部语义) -->
      <div class="flex shrink-0 items-center justify-center border-t py-1.5">
        <button
          class="flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          title="收起聊天面板"
          @click="close"
        >
          <PanelRightClose class="h-3.5 w-3.5" />收起
        </button>
      </div>
    </div>

    <!-- 收起后的悬浮展开按钮 -->
    <button
      v-if="!open"
      class="absolute bottom-4 right-4 z-20 flex h-9 items-center gap-1.5 rounded-full border border-border bg-card px-3.5 text-xs font-medium shadow-md transition-all hover:bg-accent"
      :title="buttonLabel"
      @click="open = true"
    >
      {{ buttonLabel }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { PanelRightClose } from "lucide-vue-next";
import { onBeforeUnmount, ref } from "vue";

const props = withDefaults(
  defineProps<{
    /** localStorage 记忆键(每页唯一) */
    storageKey: string;
    defaultWidth?: number;
    min?: number;
    max?: number;
    buttonLabel?: string;
    /** 初始折叠(仅初始态,不持久化)。单元页默认收起;practice 等页面不传 → 保持展开 */
    startCollapsed?: boolean;
    /** 视口宽度低于该值时自动收起(仅向下越过阈值时收起一次,不阻止用户重新展开) */
    collapseBelow?: number;
  }>(),
  {
    defaultWidth: 360,
    min: 280,
    max: 700,
    buttonLabel: "助手",
    startCollapsed: false,
    collapseBelow: undefined,
  },
);

function loadWidth(): number {
  try {
    const v = Number(localStorage.getItem(`chatpanel:${props.storageKey}`));
    if (Number.isFinite(v) && v >= props.min && v <= props.max) return v;
  } catch {
    /* ignore */
  }
  return props.defaultWidth;
}

const open = ref(!props.startCollapsed);
const width = ref(loadWidth());

// ── 窄屏自动收起(单向: 越过阈值收起,不阻止用户重新展开) ──
let narrowQuery: MediaQueryList | null = null;
function handleNarrowChange(ev: MediaQueryListEvent) {
  if (ev.matches) open.value = false;
}
if (props.collapseBelow !== undefined) {
  narrowQuery = window.matchMedia(`(max-width: ${props.collapseBelow}px)`);
  if (narrowQuery.matches) open.value = false;
  narrowQuery.addEventListener("change", handleNarrowChange);
}

function close() {
  open.value = false;
}

let moveHandler: ((ev: MouseEvent) => void) | null = null;
let upHandler: (() => void) | null = null;

function startResize(e: MouseEvent) {
  e.preventDefault();
  const startX = e.clientX;
  const startWidth = width.value;

  moveHandler = (ev: MouseEvent) => {
    // 右面板: 拖左(分隔条左移)变大, 拖右变小
    const next = Math.min(
      props.max,
      Math.max(props.min, startWidth + (startX - ev.clientX)),
    );
    width.value = next;
  };
  upHandler = () => {
    if (moveHandler) document.removeEventListener("mousemove", moveHandler);
    if (upHandler) document.removeEventListener("mouseup", upHandler);
    moveHandler = null;
    upHandler = null;
    try {
      localStorage.setItem(
        `chatpanel:${props.storageKey}`,
        String(Math.round(width.value)),
      );
    } catch {
      /* ignore */
    }
  };
  document.addEventListener("mousemove", moveHandler);
  document.addEventListener("mouseup", upHandler);
}

onBeforeUnmount(() => {
  if (moveHandler) document.removeEventListener("mousemove", moveHandler);
  if (upHandler) document.removeEventListener("mouseup", upHandler);
  if (narrowQuery)
    narrowQuery.removeEventListener("change", handleNarrowChange);
});

defineExpose({
  open,
  toggle: () => {
    open.value = !open.value;
  },
  expand: () => {
    open.value = true;
  },
});
</script>
