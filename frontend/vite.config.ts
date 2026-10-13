import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, "VITE_");
  // 默认 8002 对齐 start.py/后端 .env 的 PORT=8002:
  // 新克隆无本地 frontend/.env(被 gitignore)时,回落 8000 会让所有 /api 请求 500,
  // 前端表现为「后端没启动」——评委双击 start.bat 必踩
  const backendPort = env.VITE_BACKEND_PORT || "8002";

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
      },
    },
    server: {
      port: 5174,
      watch: {
        // 编辑工具/部分 IDE 落盘时会先写临时文件或临时目录。Windows 上 watcher 撞到
        // 被占用的临时路径会直接抛 EBUSY 并**终止 dev server**（本机实测崩了三次）。
        // 在配置层排除这些路径，比「崩一次重启一次」靠谱。
        ignored: ["**/*.tmpdir/**", "**/*.tmp", "**/.*.tmp"],
      },
      // 开发期强制不缓存: 部分浏览器(360/搜狗/Edge 增强缓存)会忽略 no-cache
      // 导致「框架是旧的、资料空白」类问题,no-store 从根上禁止复用缓存
      headers: {
        "Cache-Control": "no-store",
      },
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
          ws: true,
        },
      },
      hmr: {
        overlay: false,
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      include: ["src/**/*.test.ts"],
    },
  };
});
