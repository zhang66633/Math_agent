/**
 * request 封装测试 — JWT 注入 + 401 全局处理（安全相关）。
 *
 * 用自定义 axios adapter 模拟响应，不走网络。
 * 401 分支会清本地会话并跳登录——这是「token 失效后不再携带凭据」的
 * 安全护栏，白名单（/auth/*）与防重入标志都必须锁死。
 */

import { AxiosError, AxiosHeaders } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

/** 构造带指定状态码的 AxiosError（与真实响应错误同构） */
function makeError(status: number, url: string): AxiosError {
  const config = {
    url,
    headers: new AxiosHeaders(),
  } as unknown as AxiosError["config"];
  const response = { status, data: {} } as AxiosError["response"];
  return new AxiosError(
    "mock",
    AxiosError.ERR_BAD_RESPONSE,
    config,
    null,
    response,
  );
}

/** 记录最近一次请求配置的 adapter 工厂 */
function capturingAdapter(status: number | null) {
  return vi.fn(async (config: Record<string, unknown>) => {
    (globalThis as Record<string, unknown>).__lastConfig = config;
    if (status === null) {
      return { data: { ok: true }, status: 200, config, headers: {} };
    }
    throw makeError(status, String(config.url ?? ""));
  });
}

async function freshRequest() {
  vi.resetModules();
  return (await import("./request")).default;
}

describe("JWT 注入", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("有 token 时自动带 Authorization: Bearer 头", async () => {
    localStorage.setItem("mma:token", "jwt-abc123");
    const service = await freshRequest();
    service.defaults.adapter = capturingAdapter(null);
    await service.get("/knowledge/stats");
    const cfg = (globalThis as Record<string, unknown>).__lastConfig as {
      headers: AxiosHeaders;
    };
    expect(cfg.headers.get("Authorization")).toBe("Bearer jwt-abc123");
  });

  it("无 token 时不带 Authorization 头", async () => {
    const service = await freshRequest();
    service.defaults.adapter = capturingAdapter(null);
    await service.get("/knowledge/stats");
    const cfg = (globalThis as Record<string, unknown>).__lastConfig as {
      headers: AxiosHeaders;
    };
    expect(cfg.headers.get("Authorization")).toBeFalsy();
  });
});

describe("401 全局处理", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it("非 /auth 的 401 → 清本地会话三件套", async () => {
    localStorage.setItem("mma:token", "expired");
    localStorage.setItem("mma-chat-sessions", "[]");
    localStorage.setItem("mma:nickname", "哲");
    const service = await freshRequest();
    service.defaults.adapter = capturingAdapter(401);
    // jsdom 不实现跳转，会往 stderr 打警告——压掉保持 CI 输出干净
    const navWarn = vi.spyOn(console, "error").mockImplementation(() => {});
    await expect(service.get("/tasks")).rejects.toThrow();
    navWarn.mockRestore();
    expect(localStorage.getItem("mma:token")).toBeNull();
    expect(localStorage.getItem("mma-chat-sessions")).toBeNull();
    expect(localStorage.getItem("mma:nickname")).toBeNull();
  });

  it("/auth/* 的 401 不清会话（登录流程正常返回）", async () => {
    localStorage.setItem("mma:token", "expired");
    const service = await freshRequest();
    service.defaults.adapter = capturingAdapter(401);
    await expect(service.get("/auth/user")).rejects.toThrow();
    expect(localStorage.getItem("mma:token")).toBe("expired");
  });

  it("500 不清会话、原样 reject", async () => {
    localStorage.setItem("mma:token", "valid");
    const service = await freshRequest();
    service.defaults.adapter = capturingAdapter(500);
    await expect(service.get("/tasks")).rejects.toThrow();
    expect(localStorage.getItem("mma:token")).toBe("valid");
  });

  it("并发 401 只清一次（防重入标志）", async () => {
    localStorage.setItem("mma:token", "expired");
    const service = await freshRequest();
    service.defaults.adapter = capturingAdapter(401);
    // 第一次 401 后 _authRedirecting=true；重新写入 token 模拟第二个并发请求
    await expect(service.get("/tasks")).rejects.toThrow();
    localStorage.setItem("mma:token", "expired-2");
    await expect(service.get("/tasks")).rejects.toThrow();
    // 第二次不清（防重入）——token 仍在
    expect(localStorage.getItem("mma:token")).toBe("expired-2");
  });
});
