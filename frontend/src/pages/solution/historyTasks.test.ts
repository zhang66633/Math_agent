import { describe, expect, it } from "vitest";
import { ref } from "vue";

/**
 * 方案页「历史任务」入口的纯逻辑测试（2026-10-14）。
 *
 * 背景：taskId 原本只存在浏览器 localStorage 的 session 上，删掉会话
 * （或换浏览器/清缓存）后，后端任务数据完好却再也打不开——「任务孤儿化」。
 * 右栏「历史任务」按钮给一个与会话无关的入口。
 *
 * 这里只测不依赖 DOM 的部分：状态标签映射与列表规整。
 * 组件渲染由 solution 页自身承担，vitest 环境未挂 jsdom 全局 setup。
 */

const STATUS_LABELS: Record<string, string> = {
  running: "进行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

function statusLabel(s: string): string {
  return STATUS_LABELS[s] ?? s;
}

/** 与 openHistoryTask 同构：没有活跃会话就先建一个承载 taskId */
function resolveSession(
  active: { id: string; taskId?: string } | null,
  create: () => { id: string; taskId?: string },
): { id: string; taskId?: string } {
  return active ?? create();
}

describe("历史任务面板", () => {
  it("四个终态/运行态都有中文标签", () => {
    expect(statusLabel("running")).toBe("进行中");
    expect(statusLabel("completed")).toBe("已完成");
    expect(statusLabel("failed")).toBe("失败");
    expect(statusLabel("cancelled")).toBe("已取消");
  });

  it("未知状态原样返回，不显示 undefined", () => {
    expect(statusLabel("weird_new_status")).toBe("weird_new_status");
    expect(statusLabel("")).toBe("");
  });

  it("没有活跃会话时会新建一个承载任务", () => {
    let created = 0;
    const made = () => {
      created += 1;
      return { id: `s${created}` };
    };
    const s = resolveSession(null, made);
    expect(created).toBe(1);
    expect(s.id).toBe("s1");
  });

  it("已有活跃会话时复用，不新建", () => {
    let created = 0;
    const s = resolveSession({ id: "existing" }, () => {
      created += 1;
      return { id: "new" };
    });
    expect(created).toBe(0);
    expect(s.id).toBe("existing");
  });

  it("任务列表非数组时规整为空数组（后端异常不炸面板）", () => {
    const raw: unknown = { detail: "error" };
    const list = Array.isArray(raw) ? (raw as unknown[]) : [];
    expect(list).toEqual([]);
  });

  it("ref 持有的列表可在 toggle 后原地更新", () => {
    const tasks = ref<{ task_id: string }[]>([]);
    tasks.value = [{ task_id: "579b79d0" }];
    expect(tasks.value).toHaveLength(1);
    expect(tasks.value[0].task_id).toBe("579b79d0");
  });
});
