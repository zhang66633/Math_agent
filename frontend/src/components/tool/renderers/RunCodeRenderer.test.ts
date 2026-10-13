/**
 * RunCodeRenderer 组件测试 —— 图表去重与「折叠进推理过程」。
 *
 * 用户报的是视觉问题（"同一张图出现两次"），纯函数单测只能证明 URL 去重了，
 * 证明不了 DOM 里真的只渲染一张、且方案模式下默认收起。这里 mount 出来数 <img>。
 */

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import RunCodeRenderer from "./RunCodeRenderer.vue";

const OUTPUT = [
  {
    name: "run_code",
    preview: "输出:\n计算完成",
    // 实测形状：同一张图被 stdout 与文件清单各报一次
    images: ["/api/images/run1/fig1.png", "/api/images/run1/fig1.png"],
  },
];

function render(props: Record<string, unknown> = {}) {
  return mount(RunCodeRenderer, {
    props: { input: null, output: OUTPUT, status: "success", ...props },
  });
}

describe("RunCodeRenderer 图表渲染", () => {
  it("重复 URL 只渲染一张图（chat 模式，默认展开）", () => {
    const w = render();
    const imgs = w.findAll("img");
    expect(imgs).toHaveLength(1);
    expect(imgs[0].attributes("src")).toBe("/api/images/run1/fig1.png");
    // 不折叠时不出现展开按钮
    expect(w.text()).not.toContain("展开图表");
  });

  it("foldImages=true 时默认收起，只留一行可展开标记", async () => {
    const w = render({ foldImages: true });
    expect(w.findAll("img")).toHaveLength(0);
    expect(w.text()).toContain("展开图表（1 张）");

    await w.find("button[type='button']").trigger("click");
    expect(w.findAll("img")).toHaveLength(1);
    expect(w.text()).toContain("收起图表");
  });

  it("没有图表时不出现折叠控件（不占版面）", () => {
    const w = render({
      foldImages: true,
      output: [{ name: "run_code", preview: "无图" }],
    });
    expect(w.text()).not.toContain("展开图表");
    expect(w.findAll("img")).toHaveLength(0);
  });
});
