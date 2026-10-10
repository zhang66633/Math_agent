import { AgentType } from "@/types/enum";
/**
 * Agent 身份配置 — 颜色、lucide 图标、中文标签
 *
 * 用于 BubbleAvatar（头像图标 + 颜色点）与 BubbleAgent（标签颜色 + 流式指示）。
 * 2026-09：emoji 全部替换为 lucide-vue-next 组件（跨平台渲染一致、可随主题配色）。
 */
import {
  BarChart3,
  Calculator,
  Compass,
  Crosshair,
  type LucideIcon,
  Microscope,
  PenLine,
  ShieldCheck,
  Terminal,
  Zap,
} from "lucide-vue-next";

export interface AgentIdentityConfig {
  /** Tailwind 背景色 class（颜色点、脉冲指示器） */
  color: string;
  /** lucide 图标组件（替代原 emoji） */
  icon: LucideIcon;
  /** 中文简称 */
  label: string;
  /** Tailwind 文字颜色 class */
  textColor: string;
}

export const AGENT_IDENTITY: Record<AgentType, AgentIdentityConfig> = {
  [AgentType.ORCHESTRATOR]: {
    color: "bg-violet-500",
    icon: Crosshair,
    label: "主控",
    textColor: "text-violet-600 dark:text-violet-400",
  },
  [AgentType.ANALYSIS]: {
    color: "bg-blue-500",
    icon: Microscope,
    label: "分析",
    textColor: "text-blue-600 dark:text-blue-400",
  },
  [AgentType.MODELING]: {
    color: "bg-emerald-500",
    icon: Calculator,
    label: "建模",
    textColor: "text-emerald-600 dark:text-emerald-400",
  },
  [AgentType.SOLVING]: {
    color: "bg-amber-500",
    icon: Zap,
    label: "求解",
    textColor: "text-amber-600 dark:text-amber-400",
  },
  [AgentType.VERIFICATION]: {
    color: "bg-rose-500",
    icon: ShieldCheck,
    label: "验证",
    textColor: "text-rose-600 dark:text-rose-400",
  },
  [AgentType.WRITING]: {
    color: "bg-cyan-500",
    icon: PenLine,
    label: "写作",
    textColor: "text-cyan-600 dark:text-cyan-400",
  },
};

/** 根据 agent_type 获取身份配置，无匹配返回 null */
export function getAgentIdentity(
  agentType?: AgentType,
): AgentIdentityConfig | null {
  if (!agentType) return null;
  return AGENT_IDENTITY[agentType] ?? null;
}

/** 学习/导航类角色 → 图标（learn 页 agentMap 与 AgentIdentity 之外的扩展角色） */
export const ROLE_ICONS: Record<string, LucideIcon> = {
  navigator: Compass,
  analyst: Microscope,
  modeler: Calculator,
  solver: Terminal,
  verifier: ShieldCheck,
  editor: PenLine,
  butler: BarChart3,
};
