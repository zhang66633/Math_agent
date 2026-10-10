/**
 * Markdown 渲染管线测试 — 安全红线 + 渲染正确性。
 *
 * 本文件是全项目 LLM 内容进 DOM 的唯一通道（RULES 安全红线：
 * LLM 内容渲染必须过 DOMPurify）。XSS 用例是护栏——若白名单漂移
 * （MARKDOWN_SANITIZE_CONFIG 被改坏），这些用例立即红。
 */

import { describe, expect, it } from "vitest";
import {
  MARKDOWN_SANITIZE_CONFIG,
  extractToc,
  renderMarkdown,
  renderMarkdownAsync,
} from "./markdown";

describe("XSS 防护（安全红线）", () => {
  it("清除 <script> 标签", () => {
    const html = renderMarkdown("hello <script>alert(1)</script> world");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("alert(1)");
    expect(html).toContain("hello");
  });

  it("剥掉 img 的 onerror 事件属性", () => {
    const html = renderMarkdown('<img src="x" onerror="alert(1)">');
    expect(html).not.toContain("onerror");
    expect(html).not.toContain("alert(1)");
  });

  it("中性化 javascript: 协议链接", () => {
    const html = renderMarkdown("[click me](javascript:alert(1))");
    expect(html.toLowerCase()).not.toContain("javascript:");
    expect(html).not.toContain("alert(1)");
  });

  it("清除 iframe / svg onload 等危险载荷", () => {
    const html = renderMarkdown(
      '<iframe src="https://evil.com"></iframe><svg onload="alert(1)"></svg>',
    );
    expect(html).not.toContain("<iframe");
    expect(html).not.toContain("evil.com");
    expect(html).not.toContain("onload");
  });

  it("data: 协议的 script 载体被清除", () => {
    const html = renderMarkdown(
      '<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>',
    );
    expect(html.toLowerCase()).not.toContain("data:text/html");
  });

  it("清洗配置本身包含 MathML/Katex 白名单（防配置漂移）", () => {
    expect(MARKDOWN_SANITIZE_CONFIG.USE_PROFILES).toMatchObject({
      html: true,
      svg: true,
      mathMl: true,
    });
    expect(MARKDOWN_SANITIZE_CONFIG.ADD_ATTR).toContain("xmlns");
  });
});

describe("正常 Markdown 渲染", () => {
  it("粗体 / 行内代码 / 链接（同步路径）", () => {
    expect(renderMarkdown("**重点**")).toContain("<strong>重点</strong>");
    expect(renderMarkdown("`code`")).toContain("<code>code</code>");
    const link = renderMarkdown("[文档](https://example.com/a)");
    expect(link).toContain('href="https://example.com/a"');
  });

  it("空输入返回空串", async () => {
    expect(renderMarkdown("")).toBe("");
    await expect(renderMarkdownAsync("")).resolves.toBe("");
  });

  it("同输入命中缓存（引用稳定）", () => {
    const a = renderMarkdown("缓存测试 **x**");
    const b = renderMarkdown("缓存测试 **x**");
    expect(a).toBe(b);
  });
});

describe("自定义渲染器（异步路径：标题锚点 + 表格 wrapper）", () => {
  // 注意：锚点 id 与 table-wrapper 只在 renderMarkdownAsync 使用的
  // paperRenderer 里；同步 renderMarkdown 走 marked 默认渲染器（聊天气泡
  // 场景不需要目录，这是既定的双路径设计）。
  it("标题带锚点 id", async () => {
    const html = await renderMarkdownAsync("# 建模方法");
    expect(html).toContain("<h1");
    expect(html).toContain('id="建模方法"');
    expect(html).toContain("建模方法");
  });

  it("表格走自定义渲染器（wrapper + min-w-full）", async () => {
    const html = await renderMarkdownAsync("| a | b |\n|---|---|\n| 1 | 2 |");
    expect(html).toContain("table-wrapper");
    expect(html).toContain("min-w-full");
    expect(html).toContain("<td>1</td>");
  });

  it("代码块经 highlight 渲染后仍是转义安全文本", async () => {
    const html = await renderMarkdownAsync("```python\nprint('<b>')\n```");
    expect(html).toContain("<pre");
    expect(html).toContain("&lt;b&gt;"); // 尖括号必须转义
    expect(html).not.toContain("<b>"); // 不得出现未转义标签
  });
});

describe("KaTeX 公式", () => {
  it("行内与块级公式渲染为 .katex", () => {
    const html = renderMarkdown("行内 $E=mc^2$ 与块级 $$\\min Z = c^Tx$$");
    expect(html).toContain('class="katex"');
    expect(html).toContain("katex-display");
    expect(html).not.toContain("katex-error");
  });

  it("坏公式不崩溃（throwOnError=false 产出错误占位而非抛异常）", () => {
    expect(() => renderMarkdown("$\\frac{1}{}$")).not.toThrow();
  });
});

describe("extractToc", () => {
  it("从异步渲染结果提取 h1-h3 目录（锚点由 paperRenderer 生成）", async () => {
    const html = await renderMarkdownAsync(
      "# 问题重述\n## 模型建立\n### 4.1 子问题",
    );
    const toc = extractToc(html);
    expect(toc.length).toBe(3);
    expect(toc[0]).toMatchObject({ level: 1 });
    expect(toc[1]).toMatchObject({ level: 2 });
    expect(toc[2]).toMatchObject({ level: 3 });
    expect(toc[0].text).toContain("问题重述");
  });
});
