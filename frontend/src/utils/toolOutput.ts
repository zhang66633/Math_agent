import type { ToolOutputEntry } from "@/types/response";

/**
 * 工具输出的图表 URL 提取 —— 前端唯一的去重入口。
 *
 * 为什么要去重：后端 `run_code` 的 stdout 里常把图表 URL 打印一次，
 * 工具又把它列进 `images`，同一个 URL 会在一条 tool_result 里出现两次
 * （实测事件流 12df70f4：`images` 为 `[q2_route.png, q2_route.png]`）。
 * 旧实现直接把数组交给 `<img v-for>`，同一张图渲染两遍——用户看到
 * 「图表重复出现」。这里按 URL 保序去重，抹掉重复源。
 */
export function collectImageUrls(
  output: unknown[] | null | undefined,
): string[] {
  if (!Array.isArray(output)) return [];
  const urls: string[] = [];
  for (const entry of output as ToolOutputEntry[]) {
    if (!entry || !Array.isArray(entry.images)) continue;
    for (const url of entry.images) {
      if (typeof url === "string" && url && !urls.includes(url)) urls.push(url);
    }
  }
  return urls;
}
