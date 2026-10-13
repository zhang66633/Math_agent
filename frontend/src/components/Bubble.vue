<script setup lang="ts">
import BubbleAgent from "@/components/bubble/BubbleAgent.vue";
import BubbleClarify from "@/components/bubble/BubbleClarify.vue";
import BubbleSystem from "@/components/bubble/BubbleSystem.vue";
import BubbleTool from "@/components/bubble/BubbleTool.vue";
import BubbleUser from "@/components/bubble/BubbleUser.vue";
import { useChatSessionStore } from "@/stores/chatSession";
import type { Message } from "@/types/response";
/**
 * 消息气泡 — 按 msg_type 分发到对应子组件
 *
 *   user     → BubbleUser
 *   agent    → BubbleAgent（含 Markdown / 打字机 / 论文操作 + 内联工具卡片）
 *   tool     → BubbleTool（含输入 / 输出 / 图表）
 *   system   → BubbleSystem（含图标 / 摘要）
 *   clarify  → BubbleClarify（含澄清卡片）
 */
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    message: Message;
    isLast?: boolean;
    /** 折叠工具卡片里的图表（方案模式：图表在论文正文还会出现一次） */
    foldToolImages?: boolean;
  }>(),
  { isLast: false, foldToolImages: false },
);

const emit = defineEmits<{
  openPaper: [];
  retry: [];
}>();

const chatSession = useChatSessionStore();

// chat 模式：agent 气泡下挂内联工具卡片（dsh 式"工具嵌在输出中"）
const attachedTools = computed<Message[]>(() =>
  props.message.msg_type === "agent"
    ? chatSession.getToolAttachments(props.message.id)
    : [],
);

// chat 模式：片段流（文本与工具按事件顺序交错），渲染时按序输出
const agentSegments = computed(() =>
  props.message.msg_type === "agent"
    ? chatSession.getAgentSegments(props.message.id)
    : [],
);

const component = computed(() => {
  switch (props.message.msg_type) {
    case "user":
      return BubbleUser;
    case "agent":
      return BubbleAgent;
    case "tool":
      return BubbleTool;
    case "system":
      return BubbleSystem;
    case "clarify":
      return BubbleClarify;
    default:
      return BubbleSystem;
  }
});
</script>

<template>
  <component
    :is="component"
    :message="message"
    :is-last="isLast"
    :attached-tools="attachedTools"
    :segments="agentSegments"
    :fold-tool-images="foldToolImages"
    @open-paper="emit('openPaper')"
    @retry="emit('retry')"
  />
</template>
