import type {
  LearningPath,
  LearningPhase,
  LearningUnit,
} from "@/apis/learningApi";
import {
  fetchLearningPath,
  fetchUnitDetail,
  markUnitComplete,
  saveRoleToProfile,
} from "@/apis/learningApi";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

export type { LearningPath, LearningUnit, LearningPhase };

export type AgentRole = "modeler" | "programmer" | "writer";

export const useLearningStore = defineStore("learning", () => {
  // ── 状态 ──────────────────────────────────────────
  const currentRole = ref<AgentRole>("modeler");
  const path = ref<LearningPath | null>(null);
  const currentUnit = ref<LearningUnit | null>(null);
  const loading = ref(false);
  const error = ref("");

  // ── 计算属性 ──────────────────────────────────────
  // 曾经这里有 totalUnits/completedUnits/progressPercent 三个计算属性，来源是
  // LearningPath.total_units / completed_units —— 但后端 /learning/path/{role}
  // 从不返回这两个字段（只返回 phases/generated_at/path_id/role/user_id），
  // 于是它们恒为 0，且没有任何页面消费（LearningDoc.vue 里同名的 progressPercent
  // 是它自己根据滚动位置算的，与此无关）。审计 2026-10-14 清理：死字段不补默认值
  // 充数，要么后端真返回，要么删掉。
  const skillTree = computed(() => {
    if (!path.value) return [];
    return path.value.phases.map((phase: LearningPhase) => ({
      name: phase.name,
      expanded: true,
      units: phase.units.map((u: LearningUnit) => ({
        id: u.unit_id,
        name: u.title,
        // pending（未学）显示为可学态而非锁定——审查 P0-3：假锁会让 61 个单元
        // 永远带锁图标、进度恒 0。真正的解锁顺序约束由路径阶段划分体现。
        status:
          u.status === "completed"
            ? ("completed" as const)
            : ("active" as const),
        difficulty: u.difficulty,
      })),
    }));
  });

  // ── 操作 ──────────────────────────────────────────
  async function loadPath(role?: AgentRole) {
    const r = role ?? currentRole.value;
    loading.value = true;
    error.value = "";
    try {
      const res = await fetchLearningPath(r);
      path.value = res.data.path;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      error.value = msg || "加载学习路径失败";
    } finally {
      loading.value = false;
    }
  }

  async function loadUnit(unitId: string) {
    loading.value = true;
    error.value = "";
    try {
      const res = await fetchUnitDetail(unitId);
      currentUnit.value = res.data.unit;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      error.value = msg || "加载学习单元失败";
    } finally {
      loading.value = false;
    }
  }

  /** 标记单元完成（调用后端 API） */
  async function markComplete(unitId: string) {
    try {
      const res = await markUnitComplete(unitId);
      // 更新本地状态
      if (currentUnit.value && currentUnit.value.unit_id === unitId) {
        currentUnit.value.status = "completed";
        currentUnit.value.mastery_score = res.data?.mastery ?? 1.0;
      }
      // 刷新路径
      await loadPath();
      return res.data;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      error.value = msg || "标记完成失败";
      throw e;
    }
  }

  async function switchRole(role: AgentRole) {
    currentRole.value = role;
    currentUnit.value = null;
    await loadPath(role);
    // 把角色同步到服务端画像：否则 GET /profile 的 roles 恒为空，首页「继续学习」
    // 卡永远不显示（审计 2026-10-14 第 11.2 节）。本地切换优先，写画像失败只警告
    // 不阻断——它是后台同步，不是主线功能。
    try {
      await saveRoleToProfile(role);
    } catch (e) {
      console.warn("角色写入服务端画像失败（不影响本地切换）:", e);
    }
  }

  return {
    currentRole,
    path,
    currentUnit,
    loading,
    error,
    skillTree,
    loadPath,
    loadUnit,
    markComplete,
    switchRole,
  };
});
