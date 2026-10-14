import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * 上传白名单跨端一致性测试（2026-10-14）。
 *
 * 踩过的坑：后端 ALLOWED_EXTENSIONS 加了 `.parquet`，但前端 <input accept>
 * 没同步——而 `accept` 会**在文件选择器里过滤文件**，用户根本选不中，
 * 表现为「明明支持却传不了」。演示用的 12 个附件里有 8 个 parquet，
 * 这条不同步会直接挡住演示。
 *
 * 前端无法在运行时知道后端白名单，所以这里在测试期读源码比对。
 */

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "../../../..");

function frontendAccept(): string[] {
  const vue = readFileSync(resolve(HERE, "ChatInput.vue"), "utf-8");
  const m = vue.match(/accept="([^"]+)"/);
  if (!m) throw new Error("ChatInput.vue 里找不到 accept 属性");
  return m[1]
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

function backendAllowed(): string[] {
  const py = readFileSync(
    resolve(REPO_ROOT, "backend/app/api/files.py"),
    "utf-8",
  );
  const block = py.match(/ALLOWED_EXTENSIONS\s*=\s*\{([\s\S]*?)\}/);
  if (!block) throw new Error("files.py 里找不到 ALLOWED_EXTENSIONS");
  return [...block[1].matchAll(/"(\.[a-z0-9]+)"/g)].map((m) =>
    m[1].toLowerCase(),
  );
}

describe("上传白名单跨端一致性", () => {
  it("后端白名单能被解析出来（防止测试本身空跑）", () => {
    const allowed = backendAllowed();
    expect(allowed.length).toBeGreaterThan(8);
    expect(allowed).toContain(".csv");
    expect(allowed).toContain(".parquet");
  });

  it("前端 accept 必须覆盖后端允许的每一种扩展名", () => {
    const accept = frontendAccept();
    const allowed = backendAllowed();
    const missing = allowed.filter((e) => !accept.includes(e));
    expect(
      missing,
      `前端 <input accept> 缺少这些扩展名，用户会在文件选择器里选不中：${missing.join(", ")}`,
    ).toEqual([]);
  });

  it(".parquet 必须在前端 accept 里（演示附件的主要格式）", () => {
    expect(frontendAccept()).toContain(".parquet");
  });

  it("前端不应放宽到后端不接受的后缀（会白传一趟再报错）", () => {
    const accept = frontendAccept();
    const allowed = backendAllowed();
    const extra = accept.filter((e) => !allowed.includes(e));
    expect(
      extra,
      `前端 accept 比后端宽松，用户选了会被后端拒：${extra.join(", ")}`,
    ).toEqual([]);
  });
});
