/**
 * DeliverablesPanel 组件测试 —— 交付物分组的用户可见规则。
 *
 * 直接对应两条线上问题：
 *   · 右栏把上传附件、数据文件、网页报告、结果包混成一堆，用户找不到东西；
 *   · 同一张图跑过多轮 → 两份文件平铺，分不清哪张真进了论文正文。
 */

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DeliverablesPanel, { type TaskFile } from "./DeliverablesPanel.vue";

const FILES: TaskFile[] = [
  {
    type: "figure",
    name: "fig1--aaaa.png",
    url: "/api/task_files/t/fig1--aaaa.png",
    size: 2048,
  },
  {
    type: "figure",
    name: "fig1--bbbb.png",
    url: "/api/task_files/t/fig1--bbbb.png",
    size: 4096,
  },
  {
    type: "xlsx",
    name: "results--cccc.xlsx",
    url: "/api/task_files/t/results--cccc.xlsx",
    size: 7760,
  },
  { type: "uploaded", name: "题目.pdf", url: "/api/files/abc" },
  {
    type: "html",
    name: "report--dddd.html",
    url: "/api/task_files/t/report--dddd.html",
  },
  {
    type: "zip",
    name: "t_results.zip",
    url: "/api/task_files/t/t_results.zip",
  },
];

function render(props: Record<string, unknown> = {}) {
  return mount(DeliverablesPanel, {
    props: { files: FILES, completed: true, ...props },
  });
}

describe("DeliverablesPanel", () => {
  it("按类型分组，附件不混进数据文件", () => {
    const text = render().text();
    expect(text).toContain("图表 2");
    expect(text).toContain("数据文件 1");
    expect(text).toContain("报告与结果包 2");
    expect(text).toContain("上传附件 1");
    expect(text).toContain("6 个文件");
  });

  it("被正文引用的图标「正文」，未引用的标「过程」", () => {
    const w = render({
      paperMarkdown: "见图 ![图1](/api/task_files/t/fig1--bbbb.png)",
    });
    expect(w.text()).toContain("正文引用 1");
    const badges = w
      .findAll("[data-testid='figures'] button")
      .map((b) => b.text());
    expect(badges).toEqual(["过程", "正文"]);
  });

  it("论文还没生成时不误标（不出现正文徽标）", () => {
    const w = render({ paperMarkdown: "" });
    expect(w.text()).not.toContain("正文引用");
    expect(w.text()).toContain("过程");
  });

  it("文件尺寸按人类可读格式展示（图是缩略图，不显示字节数）", () => {
    const w = render({
      files: [
        {
          type: "figure",
          name: "f.png",
          url: "/api/task_files/t/f.png",
          size: 2048,
        },
        {
          type: "xlsx",
          name: "results--cccc.xlsx",
          url: "/api/task_files/t/r.xlsx",
          size: 7760,
        },
        {
          type: "zip",
          name: "t_results.zip",
          url: "/api/task_files/t/z.zip",
          size: 1300000,
        },
      ],
    });
    const text = w.text();
    expect(text).toContain("8 KB");
    expect(text).toContain("1.2 MB");
    // 图表网格只有缩略图与正文/过程徽标，不显示 "2 KB"
    expect(text).not.toContain("2 KB");
  });

  it("点击缩略图抛出 preview 事件，带原始 URL", async () => {
    const w = render();
    await w.findAll("[data-testid='figures'] button")[1].trigger("click");
    expect(w.emitted("preview")?.[0]).toEqual([
      "/api/task_files/t/fig1--bbbb.png",
    ]);
  });

  it("完成后才给文档导出，且只在真有 xlsx/csv 时出现对应按钮", () => {
    const done = render().text();
    expect(done).toContain("文档导出");
    expect(done).toContain("Excel (.xlsx)");
    expect(done).not.toContain("CSV (.csv)");

    const running = render({ completed: false }).text();
    expect(running).not.toContain("文档导出");
  });

  it("没有文件时给的是空状态说明（跑完前后两句话不同）", () => {
    expect(render({ files: [], completed: false }).text()).toContain(
      "上传的题目/数据与生成的图表将显示在这里",
    );
    expect(render({ files: [], completed: true }).text()).toContain(
      "本任务没有生成文件",
    );
  });
});
