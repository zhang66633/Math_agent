<template>
  <div>
    <!-- 彩带庆祝 -->
    <Teleport to="body">
      <div v-if="confettiOn" class="pointer-events-none fixed inset-0 z-[60] overflow-hidden">
        <span
          v-for="p in confetti"
          :key="p.i"
          class="absolute block rounded-[2px]"
          :style="{
            left: p.left + '%',
            top: '-4%',
            width: p.w + 'px',
            height: p.h + 'px',
            background: p.color,
            animation: `confettiFall ${p.dur}s ease-in ${p.delay}s forwards`,
            transform: `rotate(${p.rot}deg)`,
          }"
        />
      </div>
      <!-- 庆祝弹窗 -->
      <div v-if="celebrating" class="fixed inset-0 z-[61] flex items-center justify-center bg-black/30" @mousedown.self="closeCelebrate">
        <div class="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-xl">
          <PartyPopper class="mx-auto mb-1 h-9 w-9 text-amber-500" />
          <p class="mb-4 text-center font-display text-lg font-medium">恭喜解锁新勋章!</p>
          <div class="mb-5 flex justify-center gap-3">
            <div
              v-for="a in newOnes"
              :key="a.id"
              class="flex w-20 flex-col items-center gap-1 rounded-md border border-border bg-background p-3"
            >
              <component :is="achievementIcon(a.icon)" class="h-7 w-7" :class="tierText(a.tier)" />
              <span class="text-xs font-medium">{{ a.name }}</span>
              <span class="text-[10px] text-muted-foreground">{{ tierLabel(a.tier) }}</span>
            </div>
          </div>
          <p class="mb-4 text-center text-xs text-muted-foreground">
            {{ praiseText }}
          </p>
          <button
            class="mx-auto block rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 transition-all"
            @click="closeCelebrate"
          >
            太棒了,继续!
          </button>
        </div>
      </div>
    </Teleport>

    <!-- 勋章墙 -->
    <div v-for="tier in tiers" :key="tier.key" class="mb-6">
      <p class="mb-3 flex items-center gap-2 font-display text-base font-medium">
        <component :is="tier.icon" class="h-4 w-4" :class="tierText(tier.key)" />{{ tier.label }}
        <span class="font-mono text-[10px] text-muted-foreground">
          {{ unlockedCount(tier.key) }}/{{ tierCount(tier.key) }}
        </span>
      </p>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div
          v-for="(a, i) in byTier(tier.key)"
          :key="a.id"
          class="relative rounded-md border p-4 text-center transition-all"
          :class="a.unlocked
            ? 'border-primary/30 bg-card'
            : 'border-border bg-muted/20'"
          :title="`${a.name}:${a.desc}`"
          v-bind="stagger.itemProps(i + tierOffset(tier.key))"
        >
          <span
            v-if="a.is_new"
            class="absolute -right-1.5 -top-1.5 rounded-full bg-red-500 px-1.5 py-0.5 text-[9px] font-bold text-white"
          >NEW</span>
          <div class="mb-1.5 flex justify-center">
            <span
              class="flex h-12 w-12 items-center justify-center rounded-full border"
              :class="a.unlocked
                ? tierRing(a.tier)
                : 'border-border bg-muted/30 opacity-40'"
            >
              <component :is="achievementIcon(a.icon)" v-if="a.unlocked" class="h-6 w-6" :class="tierText(a.tier)" />
              <Lock v-else class="h-5 w-5 text-muted-foreground" />
            </span>
          </div>
          <p class="text-xs font-medium" :class="a.unlocked ? 'text-foreground' : 'text-muted-foreground'">
            {{ a.name }}
          </p>
          <p class="mt-0.5 text-[10px] leading-4 text-muted-foreground">{{ a.desc }}</p>
          <!-- 进度 -->
          <div class="mt-2">
            <div class="h-1 overflow-hidden rounded-full bg-muted">
              <div
                class="h-full rounded-full transition-all duration-500"
                :class="a.unlocked ? 'bg-emerald-500' : 'bg-primary'"
                :style="{ width: `${Math.min(100, (a.progress / Math.max(a.target, 1)) * 100)}%` }"
              />
            </div>
            <p class="mt-1 font-mono text-[10px]" :class="a.unlocked ? 'text-emerald-500' : 'text-muted-foreground'">
              {{ a.unlocked ? `已解锁 · ${shortDate(a.unlocked_at)}` : `${a.progress}/${a.target}` }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useStaggerReveal } from "@/composables/useStaggerReveal";
import {
  BadgeCheck,
  Compass,
  Flame,
  Lock,
  type LucideIcon,
  Medal,
  Mountain,
  PartyPopper,
  Pencil,
  Sprout,
  Star,
  Swords,
  Target,
  Trophy,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

export interface AchievementItem {
  id: string;
  name: string;
  desc: string;
  /** 后端下发的语义图标 key（sprout/target/pencil/swords/flame/compass/trophy/mountain/star/badge） */
  icon: string;
  tier: "bronze" | "silver" | "gold";
  progress: number;
  target: number;
  unlocked: boolean;
  unlocked_at: string | null;
  is_new: boolean;
}

const props = defineProps<{
  achievements: AchievementItem[];
}>();
const emit = defineEmits<{ ack: [] }>();

/** 成就图标 key → lucide 组件（后端只发语义 key，渲染在前端决定） */
const ACHIEVEMENT_ICONS: Record<string, LucideIcon> = {
  sprout: Sprout,
  target: Target,
  pencil: Pencil,
  swords: Swords,
  flame: Flame,
  compass: Compass,
  trophy: Trophy,
  mountain: Mountain,
  star: Star,
  badge: BadgeCheck,
};
function achievementIcon(key: string): LucideIcon {
  return ACHIEVEMENT_ICONS[key] ?? Star;
}

const tiers = [
  { key: "bronze", label: "铜章", icon: Medal },
  { key: "silver", label: "银章", icon: Medal },
  { key: "gold", label: "金章", icon: Trophy },
] as const;

const totalCount = computed(() => Math.max(props.achievements.length, 12));
const stagger = useStaggerReveal({ count: totalCount.value, delay: 45 });

function tierOffset(key: string): number {
  const order: Record<string, number> = { bronze: 0, silver: 4, gold: 8 };
  return order[key] ?? 0;
}
function byTier(key: string) {
  return props.achievements.filter((a) => a.tier === key);
}
function tierCount(key: string) {
  return props.achievements.filter((a) => a.tier === key).length || 4;
}
function unlockedCount(key: string) {
  return props.achievements.filter((a) => a.tier === key && a.unlocked).length;
}
function tierLabel(tier: string) {
  return tier === "bronze" ? "铜章" : tier === "silver" ? "银章" : "金章";
}
function tierText(tier: string) {
  return tier === "bronze"
    ? "text-amber-600"
    : tier === "silver"
      ? "text-slate-400"
      : "text-yellow-500";
}
function tierRing(tier: string) {
  return tier === "bronze"
    ? "border-amber-600/50 bg-amber-600/10"
    : tier === "silver"
      ? "border-slate-400/50 bg-slate-400/10"
      : "border-yellow-500/60 bg-yellow-500/10";
}
function shortDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

// ── 彩带庆祝 ──────────────────────────────────────────
const newOnes = computed(() => props.achievements.filter((a) => a.is_new));
const celebrating = ref(false);
const confettiOn = ref(false);
const praiseText = computed(() => {
  const n = newOnes.value.length;
  if (n >= 2) return `一口气点亮 ${n} 枚勋章,这份坚持值得鼓掌`;
  return "每一枚勋章都是你努力的见证,继续向前!";
});

// 30 个彩带粒子(位置/颜色/时长按序号确定性生成,避免闪烁)
const confetti = Array.from({ length: 30 }, (_, i) => {
  const hue = (i * 47 + 24) % 360;
  return {
    i,
    left: (i * 37) % 100,
    w: 6 + ((i * 13) % 6),
    h: 10 + ((i * 7) % 8),
    color: `hsl(${hue}, 80%, 55%)`,
    dur: 1.8 + ((i * 11) % 14) / 10,
    delay: (i % 10) * 0.08,
    rot: (i * 53) % 360,
  };
});

function closeCelebrate() {
  celebrating.value = false;
  emit("ack");
}

onMounted(() => {
  if (newOnes.value.length > 0) {
    celebrating.value = true;
    confettiOn.value = true;
    // 彩带 3.2 秒后自动收起(弹窗保留,等用户点击关闭)
    setTimeout(() => {
      confettiOn.value = false;
    }, 3200);
  }
});
</script>

<style scoped>
@keyframes confettiFall {
  0% {
    opacity: 1;
    transform: translateY(-5vh) rotate(0deg);
  }
  100% {
    opacity: 0;
    transform: translateY(105vh) rotate(720deg);
  }
}
</style>
