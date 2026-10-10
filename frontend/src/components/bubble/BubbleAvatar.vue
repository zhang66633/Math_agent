<script setup lang="ts">
import { getAgentIdentity } from "@/components/agent/AgentIdentity";
import type { AgentMessage, Message } from "@/types/response";
import { Bot } from "lucide-vue-next";
import { computed } from "vue";

const props = defineProps<{
  message: Message;
}>();

const isUser = computed(() => props.message.msg_type === "user");
const isAgent = computed(() => props.message.msg_type === "agent");
const isSystem = computed(() => props.message.msg_type === "system");
const isTool = computed(() => props.message.msg_type === "tool");
const isClarify = computed(() => props.message.msg_type === "clarify");

const identity = computed(() => {
  if (isAgent.value)
    return getAgentIdentity((props.message as AgentMessage).agent_type);
  return null;
});

// 小助手 = chat 模式无 agent_type 的通用 agent（流水线各 Agent 有专属 identity）
const isAssistant = computed(() => isAgent.value && !identity.value);

const agentColor = computed(() => identity.value?.color ?? "");

const letter = computed(() => {
  if (isUser.value) return "U";
  if (isAgent.value) return "";
  if (isSystem.value) return "S";
  if (isTool.value) return "T";
  if (isClarify.value) return "?";
  return "A";
});
</script>

<template>
  <!-- 小助手（chat 通用 agent）：渐变圆 + 机器人头像 -->
  <div
    v-if="isAssistant"
    class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-blue-600 text-white shadow-sm"
  >
    <Bot class="h-4 w-4" />
  </div>

  <!-- 其他消息类型：方框 + lucide 图标 / 字母 -->
  <div v-else class="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-border relative">
    <!-- agent 颜色指示点 -->
    <span v-if="agentColor" class="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full border border-background" :class="agentColor" />
    <!-- agent 图标或字母 -->
    <component :is="identity.icon" v-if="identity" class="h-4 w-4" :class="identity.textColor" />
    <span v-else class="text-xs">{{ letter }}</span>
  </div>
</template>
