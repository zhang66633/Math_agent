<template>
  <div class="min-h-screen flex">
    <!-- Left decorative panel -->
    <div class="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-950 items-center justify-center p-12">
      <div class="max-w-md text-white">
        <div class="flex items-center gap-3 mb-8">
          <div class="flex h-12 w-12 items-center justify-center rounded-xl bg-white/10">
            <Github class="h-7 w-7" />
          </div>
          <div>
            <h2 class="text-2xl font-bold">{{ APP_NAME }}</h2>
            <p class="text-gray-400 text-sm">数学建模多智能体辅助系统</p>
          </div>
        </div>
        <p class="text-lg text-gray-300 leading-relaxed">
          使用 GitHub 账号一键登录，无需额外注册。登录后将验证你的项目贡献者身份。
        </p>
        <div class="mt-8 space-y-4">
          <div class="flex items-center gap-3">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
              <Shield class="h-4 w-4" />
            </div>
            <span class="text-gray-300">GitHub OAuth 安全授权 — 拉取真实账户信息</span>
          </div>
          <div class="flex items-center gap-3">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
              <Users class="h-4 w-4" />
            </div>
            <span class="text-gray-300">仅限项目贡献者 — zhang66633 & shu639</span>
          </div>
          <div class="flex items-center gap-3">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
              <Zap class="h-4 w-4" />
            </div>
            <span class="text-gray-300">管理知识库、上传内容需登录验证</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Right login panel -->
    <div class="flex flex-1 items-center justify-center px-6 py-12 bg-background">
      <div class="w-full max-w-sm">
        <!-- Mobile logo -->
        <div class="flex items-center justify-center gap-2 mb-8 lg:hidden">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <Sigma class="h-5 w-5 text-primary-foreground" />
          </div>
          <span class="font-semibold">{{ APP_NAME }}</span>
        </div>

        <!-- GitHub icon -->
        <div class="flex justify-center mb-6">
          <div class="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#24292e]">
            <Github class="h-9 w-9 text-white" />
          </div>
        </div>

        <div class="text-center mb-8">
          <h1 class="text-2xl font-bold">登录 MathModelAgent</h1>
          <p class="text-sm text-muted-foreground mt-2">
            GitHub 授权后将拉取你的账户信息并验证贡献者身份
          </p>
        </div>

        <!-- Setup error hint -->
        <div v-if="setupError" class="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <p class="font-medium mb-1 flex items-center gap-1.5"><AlertTriangle class="h-4 w-4 shrink-0" />{{ setupError.includes('无法连接') ? '连接错误' : 'GitHub OAuth 配置错误' }}</p>
          <p class="whitespace-pre-wrap">{{ setupError }}</p>
        </div>

        <!-- GitHub login button -->
        <button
          class="flex h-12 w-full items-center justify-center gap-3 rounded-xl bg-[#24292e] text-sm font-medium text-white hover:bg-[#1b1f23] transition-colors disabled:opacity-50"
          :disabled="loading"
          @click="handleGithubLogin"
        >
          <Loader2 v-if="loading" class="h-5 w-5 animate-spin" />
          <Github v-else class="h-5 w-5" />
          {{ loading ? '正在跳转 GitHub 授权...' : '使用 GitHub 账号登录' }}
        </button>

        <!-- Feature list -->
        <div class="relative my-6">
          <div class="absolute inset-0 flex items-center">
            <span class="w-full border-t" />
          </div>
          <div class="relative flex justify-center text-xs uppercase">
            <span class="bg-background px-2 text-muted-foreground">仅限以下贡献者</span>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="flex items-center gap-2 rounded-lg border p-3">
            <img
              src="https://avatars.githubusercontent.com/u/235469039"
              class="h-8 w-8 rounded-full"
            />
            <div>
              <p class="text-sm font-medium">zhang66633</p>
              <p class="text-xs text-muted-foreground">Zhang</p>
            </div>
          </div>
          <div class="flex items-center gap-2 rounded-lg border p-3">
            <img
              src="https://avatars.githubusercontent.com/u/269112767"
              class="h-8 w-8 rounded-full"
            />
            <div>
              <p class="text-sm font-medium">shu639</p>
              <p class="text-xs text-muted-foreground">Shu</p>
            </div>
          </div>
        </div>

        <!-- Back home -->
        <div class="mt-8 text-center">
          <router-link
            to="/"
            class="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft class="h-4 w-4" />
            返回首页
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from "@/stores/auth";
import { APP_NAME } from "@/types/const";
import {
  AlertTriangle,
  ArrowLeft,
  Github,
  Loader2,
  Shield,
  Sigma,
  Users,
  Zap,
} from "lucide-vue-next";
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const auth = useAuthStore();
const loading = ref(false);
const setupError = ref("");

async function handleGithubLogin() {
  loading.value = true;
  setupError.value = "";
  try {
    const data = await getAuthLogin();
    if (data.authorize_url) {
      window.location.href = data.authorize_url;
      return;
    }
    setupError.value =
      "后端返回空授权链接，请重启后端确保 .env 中 GITHUB_CLIENT_ID 和 GITHUB_CLIENT_SECRET 已填写";
  } catch (e) {
    const err = e as {
      response?: { data?: { detail?: string } };
      message?: string;
    };
    const msg =
      err?.response?.data?.detail || err?.message || "获取授权链接失败";
    // 如果是网络错误，给更明确的提示
    if (!err?.response) {
      setupError.value =
        "无法连接后端，请确认后端已启动 (http://localhost:8002)";
    } else {
      setupError.value = msg;
    }
  }
  loading.value = false;
}

import { getAuthLogin } from "@/apis/authApi";
</script>
