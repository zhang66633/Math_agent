/**
 * 纯文本预览工具 —— 列表/表格里做单行显示与 title 提示时用。
 *
 * 与 `renderMarkdown` 的分工：renderMarkdown 负责「渲染成 HTML」，
 * 本模块负责「抹平成一行纯文本」（可用于 `title` 属性、可访问性文本、
 * 列表预览），两者不可互相替代——把 HTML 塞进 title 会显示成标签。
 */

/** 把 Markdown/LaTeX 源文本抹平成单行纯文本（保留公式内容，去掉定界符与排版标记）。 */
export function plainPreview(
  input: string | null | undefined,
  max = 120,
): string {
  if (!input) return "";
  let text = input;
  // 代码块 → 内容
  text = text.replace(/```[a-zA-Z0-9_-]*\n?([\s\S]*?)```/g, "$1");
  // 图片 → alt（无 alt 则丢弃）
  text = text.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1");
  // 链接 → 文本
  text = text.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
  // 公式定界符：$$…$$ / $…$ / \(…\) 只去壳，内容保留
  text = text.replace(/\$\$/g, " ");
  text = text.replace(/\$([^$\n]+)\$/g, "$1");
  text = text.replace(/\\\(([\s\S]*?)\\\)/g, "$1");
  // LaTeX：\max → max；\, \; \! 之类间距命令直接去
  text = text.replace(/\\([a-zA-Z]+)/g, "$1");
  text = text.replace(/\\[,;!:]/g, " ");
  text = text.replace(/[{}]/g, "");
  // 行首标记：标题 / 引用 / 无序·有序列表（只吃标记，不吃正文数字）
  text = text.replace(/^\s{0,3}(?:#{1,6}\s+|[-*+>]\s+|\d{1,3}\.\s+)/gm, "");
  // 强调与行内代码标记、表格竖线
  text = text.replace(/[*_`~]/g, "");
  text = text.replace(/\|/g, " ");
  text = text.replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}…` : text;
}
