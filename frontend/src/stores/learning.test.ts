import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

// mock 掉 API 层：只验证 store 的编排行为（本地切换优先、写画像失败不阻断）
vi.mock("@/apis/learningApi", () => ({
  fetchLearningPath: vi.fn(async () => ({
    data: { path: { path_id: "p1", phases: [] } },
  })),
  fetchUnitDetail: vi.fn(),
  markUnitComplete: vi.fn(),
  saveRoleToProfile: vi.fn(async () => ({ data: { status: "ok" } })),
}));

import { saveRoleToProfile } from "@/apis/learningApi";
import { useLearningStore } from "./learning";

const mockedSave = vi.mocked(saveRoleToProfile);

describe("learning store — 角色切换写入服务端画像", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("切角色时把角色写进画像", async () => {
    const store = useLearningStore();
    await store.switchRole("writer");
    expect(store.currentRole).toBe("writer");
    expect(mockedSave).toHaveBeenCalledWith("writer");
  });

  it("每次切换都写（覆盖式主角色）", async () => {
    const store = useLearningStore();
    await store.switchRole("writer");
    await store.switchRole("programmer");
    expect(mockedSave).toHaveBeenNthCalledWith(1, "writer");
    expect(mockedSave).toHaveBeenNthCalledWith(2, "programmer");
    expect(store.currentRole).toBe("programmer");
  });

  it("写画像失败不影响本地切换与路径加载", async () => {
    mockedSave.mockRejectedValueOnce(new Error("network down"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const store = useLearningStore();
    await expect(store.switchRole("writer")).resolves.toBeUndefined();
    expect(store.currentRole).toBe("writer"); // 本地状态已切
    expect(store.path).not.toBeNull(); // 路径已加载
    expect(warn).toHaveBeenCalled(); // 失败有告警，不静默
    warn.mockRestore();
  });
});
