/**
 * 方案模式前端纯函数单测：进度文案 / 工具图表去重 / 预览文本。
 *
 * 这三条都是"用户看得见"的规则，抽成纯函数就是为了能这样直接验证：
 *   · 进度气泡再也不能出现「输出 N 字」（实现度量当结果汇报）；
 *   · 同一条 tool_result 里的重复图表 URL 只渲染一张；
 *   · 列表 title 里不出现 Markdown 标记。
 */

import { describe, expect, it } from "vitest";
import { describeNodeEnd } from "./taskSummary";
import { plainPreview } from "./text";
import { collectImageUrls } from "./toolOutput";

describe("describeNodeEnd — 进度文案", () => {
  it("论文节点报章节/图表，不报字符数", () => {
    const text = describeNodeEnd({
      title: "论文写作",
      output_length: 40315,
      sections: 7,
      figures: 6,
      red_team: "REVISED",
    });
    expect(text).toBe("论文已生成 · 7 章 · 6 张图表 · 红队修订完成");
    expect(text).not.toContain("40315");
    expect(text).not.toContain("字");
  });

  it("求解节点报图表与数据表", () => {
    const text = describeNodeEnd({
      title: "求解计算",
      output_length: 15409,
      images_count: 6,
      xlsx_count: 2,
    });
    expect(text).toBe("求解完成 · 6 张图表 · 2 个数据表");
    expect(text).not.toContain("字");
  });

  it("验证节点只看通过与否", () => {
    expect(describeNodeEnd({ passed: true, output_length: 4396 })).toBe(
      "模型检验通过",
    );
    expect(describeNodeEnd({ passed: false })).toBe("检验未通过，触发回退重做");
  });

  it("导出节点报文件数", () => {
    expect(describeNodeEnd({ files_count: 2 })).toBe("已导出 2 个结果文件");
  });

  it("无事实字段时退化为标题，不编造字符数", () => {
    expect(describeNodeEnd({ title: "问题分类", output_length: 130 })).toBe(
      "已完成：问题分类",
    );
    expect(describeNodeEnd({})).toBe("已完成");
  });

  it("跳过的节点说明跳过", () => {
    expect(describeNodeEnd({ title: "数据预处理", skipped: true })).toBe(
      "已跳过：数据预处理",
    );
  });

  it("旧任务缺 sections 字段时用红队结论兜底，正文仍不出现字符数", () => {
    const text = describeNodeEnd({
      title: "论文写作",
      output_length: 38324,
      red_team: "PASS",
    });
    expect(text).toBe("论文已生成 · 红队审校通过");
    expect(text).not.toContain("字");
  });
});

describe("collectImageUrls — 工具图表去重", () => {
  it("同一条输出里重复的 URL 只留一份且保序", () => {
    const output = [
      {
        name: "run_code",
        images: ["/api/images/r1/a.png", "/api/images/r1/a.png"],
      },
    ];
    expect(collectImageUrls(output)).toEqual(["/api/images/r1/a.png"]);
  });

  it("跨条目去重且保留先后顺序", () => {
    const output = [
      { name: "run_code", images: ["/api/images/r1/b.png"] },
      {
        name: "run_code",
        images: ["/api/images/r1/a.png", "/api/images/r1/b.png"],
      },
    ];
    expect(collectImageUrls(output)).toEqual([
      "/api/images/r1/b.png",
      "/api/images/r1/a.png",
    ]);
  });

  it("空输出与非数组输出不炸", () => {
    expect(collectImageUrls(null)).toEqual([]);
    expect(collectImageUrls(undefined)).toEqual([]);
    expect(collectImageUrls([{ name: "x" }])).toEqual([]);
    expect(collectImageUrls([{ images: [123, ""] }])).toEqual([]);
  });
});

describe("plainPreview — 列表预览纯文本", () => {
  it("去掉 Markdown 标记、保留公式内容", () => {
    const text = plainPreview(
      "**求解** $\\max z = 3x_1 + 2x_2$ 的[最优解](http://x)",
    );
    expect(text).toContain("求解");
    expect(text).toContain("max z = 3x1 + 2x2");
    expect(text).not.toContain("**");
    expect(text).not.toContain("http");
  });

  it("保留行首有意义的数字（列表标记才被吃掉）", () => {
    expect(plainPreview("32 若把蚁群算法的挥发率设为 0")).toBe(
      "32 若把蚁群算法的挥发率设为 0",
    );
    expect(plainPreview("- 第一条\n- 第二条")).toBe("第一条 第二条");
  });

  it("超长文本截断并加省略号", () => {
    const text = plainPreview("字".repeat(50), 10);
    expect(text).toHaveLength(11);
    expect(text.endsWith("…")).toBe(true);
  });

  it("空输入返回空串", () => {
    expect(plainPreview(null)).toBe("");
    expect(plainPreview("")).toBe("");
  });
});
