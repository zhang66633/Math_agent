<script setup lang="ts">
import { type ChatFileRef, uploadChatFile } from "@/apis/chatApi";
import { Loader2, Paperclip, Send, X } from "lucide-vue-next";
import { nextTick, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    isRunning?: boolean;
    inputPlaceholder?: string;
    messagesCount?: number;
    prefill?: string;
  }>(),
  {
    isRunning: false,
    inputPlaceholder: "输入消息...",
    messagesCount: 0,
    prefill: "",
  },
);

const emit = defineEmits<{
  send: [text: string, files?: ChatFileRef[]];
}>();

const inputText = ref("");
const textareaRef = ref<HTMLTextAreaElement | null>(null);

// 接收外部预填文本
watch(
  () => props.prefill,
  (v) => {
    if (v) {
      inputText.value = v;
      nextTick(() => {
        textareaRef.value?.focus();
        autoResize();
      });
    }
  },
);
const fileInputRef = ref<HTMLInputElement | null>(null);
const attachedFiles = ref<ChatFileRef[]>([]);
const uploading = ref(false);

function triggerFileInput() {
  fileInputRef.value?.click();
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  const files = input.files;
  if (!files || files.length === 0) return;

  uploading.value = true;
  try {
    for (const file of Array.from(files)) {
      if (file.size > 20 * 1024 * 1024) {
        alert(`文件 ${file.name} 超过 20MB 限制`);
        continue;
      }
      const ref = await uploadChatFile(file);
      attachedFiles.value.push(ref);
    }
  } catch (err) {
    alert(`文件上传失败: ${err instanceof Error ? err.message : err}`);
  } finally {
    uploading.value = false;
    input.value = "";
  }
}

function removeFile(index: number) {
  attachedFiles.value.splice(index, 1);
}

function autoResize() {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
}

function sendMessage() {
  const text = inputText.value.trim();
  if ((!text && attachedFiles.value.length === 0) || props.isRunning) return;
  const files =
    attachedFiles.value.length > 0 ? [...attachedFiles.value] : undefined;
  emit("send", text, files);
  inputText.value = "";
  attachedFiles.value = [];
  if (textareaRef.value) textareaRef.value.style.height = "auto";
}
</script>

<template>
  <div class="border-t border-border bg-background p-4">
    <!-- 附件预览 -->
    <div v-if="attachedFiles.length > 0" class="flex flex-wrap gap-2 mb-2">
      <div
        v-for="(f, i) in attachedFiles"
        :key="f.file_id"
        class="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2.5 py-1 text-xs"
      >
        <Paperclip class="h-3 w-3 text-muted-foreground" />
        <span class="max-w-[160px] truncate">{{ f.filename }}</span>
        <button
          class="ml-0.5 text-muted-foreground hover:text-foreground transition-colors"
          @click="removeFile(i)"
        >
          <X class="h-3 w-3" />
        </button>
      </div>
    </div>

    <div class="flex items-end gap-2" data-tour="chat-input">
      <!-- 附件按钮 -->
      <button
        class="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border bg-background hover:bg-accent transition-colors disabled:opacity-50"
        :disabled="isRunning || uploading"
        title="上传文件（CSV/Excel/Parquet/TXT/PDF 等）"
        @click="triggerFileInput"
      >
        <Loader2 v-if="uploading" class="h-4 w-4 animate-spin" />
        <Paperclip v-else class="h-4 w-4" />
      </button>
      <input
        ref="fileInputRef"
        type="file"
        class="hidden"
        multiple
        accept=".csv,.tsv,.xlsx,.xls,.parquet,.txt,.md,.json,.pdf,.py,.dat,.mat,.doc,.docx"
        @change="onFileSelected"
      />
      <textarea
        ref="textareaRef"
        v-model="inputText"
        class="flex min-h-10 max-h-40 w-full resize-none rounded-md border border-border bg-background px-4 py-2.5 text-sm leading-relaxed placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        :placeholder="inputPlaceholder"
        rows="1"
        :disabled="isRunning"
        @keydown.enter.exact.prevent="sendMessage"
        @input="autoResize"
      />
      <button
        class="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-foreground text-background hover:bg-foreground/90 transition-colors disabled:opacity-50"
        :disabled="(!inputText.trim() && attachedFiles.length === 0) || isRunning"
        @click="sendMessage"
      >
        <Send v-if="!isRunning" class="h-4 w-4" />
        <Loader2 v-else class="h-4 w-4 animate-spin" />
      </button>
    </div>
  </div>
</template>
