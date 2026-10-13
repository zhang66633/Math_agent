import { describe, expect, it } from "vitest";
import { renderFormula } from "./kbFormula";

describe("renderFormula（知识库方法卡公式渲染）", () => {
  it("裸 LaTeX 自动包 $$ 并渲染成 KaTeX", () => {
    const html = renderFormula(
      "dp[i][w] = max(dp[i-1][w], dp[i-1][w-w_i] + v_i)",
    );
    expect(html).toContain("katex");
    expect(html).not.toContain("katex-error");
  });

  it("已含 $ 的不重复包裹", () => {
    const html = renderFormula("行内 $x^2$ 混合");
    expect(html).toContain("katex");
    // 不应出现 $$$ 这种双重包裹
    expect(html).not.toContain("$$$");
  });

  it("字符串形态（名称: 公式）也渲染，不抛错", () => {
    const html = renderFormula(
      "0-1背包: dp[i][w] = max(dp[i-1][w], dp[i-1][w-w_i] + v_i)",
    );
    expect(html).toContain("katex");
    expect(html).not.toContain("katex-error");
  });

  it("空值返回空串（不渲染空公式块）", () => {
    expect(renderFormula("")).toBe("");
    expect(renderFormula(null)).toBe("");
    expect(renderFormula(undefined)).toBe("");
    expect(renderFormula("   ")).toBe("");
  });

  it("渲染结果经过 DOMPurify（脚本注入被清掉）", () => {
    const html = renderFormula("$x$ <script>alert(1)</script>");
    expect(html).not.toContain("<script>");
  });
});
