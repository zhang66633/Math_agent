/** 知识库方法卡的公式渲染helper。
 *
 *  库里 formulas 有两种历史格式：字符串形态整体在 latex 字段
 *  （如 "0-1背包: dp[i][w] = max(...)"），结构化形态是 {name, latex, description}。
 *  两种都交给统一 markdown 管线：裸 LaTeX 包一层 $$ 让 KaTeX 接手，
 *  已含 $ 的按原文渲染，避免双重包裹。
 *
 *  DOMPurify sanitize 在 renderMarkdown 内部完成，v-html 消费是安全的。
 */

import { renderMarkdown } from "@/utils/markdown";

/** 把一段 LaTeX（可能被 "名称: 公式" 前缀污染）渲染成含 .katex 的 HTML。 */
export function renderFormula(latex: string | null | undefined): string {
  const text = (latex ?? "").trim();
  if (!text) return "";
  const body = text.includes("$") ? text : `$$${text}$$`;
  return renderMarkdown(body);
}
