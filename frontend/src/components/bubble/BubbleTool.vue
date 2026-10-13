<script setup lang="ts">
import GenericRenderer from "@/components/tool/renderers/GenericRenderer.vue";
import { getToolRenderer } from "@/components/tool/toolRenderers";
import type { Message, ToolMessage, ToolStatus } from "@/types/response";
/**
 * 工具消息气泡 — 按 tool_name 分发到对应渲染器
 *
 * 渲染器注册表 → 异步加载 → 动态组件渲染。
 * 未注册的工具回退到 GenericRenderer。
 */
import { computed, defineAsyncComponent } from "vue";
import BubbleAvatar from "./BubbleAvatar.vue";

const props = defineProps<{
  message: Message;
  /** 内联模式：嵌在 agent 气泡内，隐藏头像与时间戳、去除外边距 */
  inline?: boolean;
  /** 折叠工具产物里的图表（方案模式：同一张图会在论文正文再出现一次） */
  foldImages?: boolean;
}>();

const tool = computed(() => props.message as ToolMessage);
const toolName = computed(() => tool.value.tool_name ?? "");
const toolInput = computed(() => tool.value.input);
const toolOutput = computed(() => tool.value.output);
const toolStatus = computed<ToolStatus | undefined>(() => tool.value.status);

const rendererComponent = computed(() => {
  const loader = getToolRenderer(toolName.value);
  if (!loader) return GenericRenderer;
  return defineAsyncComponent(loader);
});

const timestamp = computed(() => {
  if (!props.message.created_at) return "";
  return new Date(props.message.created_at).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
});
</script>

<template>
  <div
    class="w-full animate-in fade-in slide-in-from-bottom-2"
    :class="inline ? '' : 'flex gap-3 my-2'"
  >
    <div v-if="!inline" class="flex shrink-0 flex-col items-center self-start pt-0.5">
      <BubbleAvatar :message="message" />
    </div>
    <div class="flex-1 min-w-0">
      <div class="flex flex-col items-start">
        <component
          :is="rendererComponent"
          :input="toolInput"
          :output="toolOutput"
          :status="toolStatus"
          :duration-ms="tool.duration_ms"
          :fold-images="foldImages"
          :error-text="typeof tool.error === 'string' ? tool.error : undefined"
        />
        <span v-if="timestamp && !inline" class="font-mono text-[10px] text-muted-foreground/50 mt-0.5">{{ timestamp }}</span>
      </div>
    </div>
  </div>
</template>